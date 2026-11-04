import type { Clip, HeatPalette } from "../data/types";
import { residualColour } from "../lib/palette";

export const GRID_W = 160, GRID_H = 90;
export const MAX_JUMP = 0.08;                          // a triangle is dropped where its depths differ by more than this share (a depth jump)

/** The ZED Mini's intrinsics at full resolution, the same for all five recordings (pipeline recordings.Calibration). **Only a fallback**:
 *  pipeline task C0 writes the cell's own intrinsics into every clip's `relief` block, and `realRelief.test.ts` holds the two equal
 *  within 0.001 on all 35 clips. The principal point is 52 px right of the frame's centre, so it must never be taken as the centre. */
export const REAL_INTRINSICS = { fx: 1433.347, cx: 1156.798, cy: 631.871 };
export interface CellIntrinsics { fx: number; fy: number; cx: number; cy: number }

/** pipeline mapping.box_intrinsics for a 160 x 90 cell: the real intrinsics through the box (x0, y0, w, h) in real-pixel edge coordinates. */
export function fallbackIntrinsics(box: [number, number, number, number], w = GRID_W, h = GRID_H): CellIntrinsics {
  const [x0, y0, bw, bh] = box, sx = w / bw, sy = h / bh;
  return {
    fx: REAL_INTRINSICS.fx * sx, fy: REAL_INTRINSICS.fx * sy,
    cx: REAL_INTRINSICS.cx * sx + (0.5 - x0) * sx - 0.5, cy: REAL_INTRINSICS.cy * sy + (0.5 - y0) * sy - 0.5,
  };
}

/** The cell's intrinsics: the clip's own, from the relief block (pipeline task C0), else the pinned fallback. */
export function cellIntrinsics(clip: Clip): CellIntrinsics {
  const { fx, fy, cx, cy } = clip.relief;
  return [fx, fy, cx, cy].every((v) => typeof v === "number" && Number.isFinite(v))
    ? { fx: fx!, fy: fy!, cx: cx!, cy: cy! } : fallbackIntrinsics(clip.relief.box);
}

export interface Pose { x: number; y: number; z: number; yawDeg: number }

/** The camera at frame f from clips.json: position (path) and yaw. Pitch and roll are not in the assets, so they are taken as zero.
 *  null from the first unverifiable frame on: nothing is placed there. */
export function poseAt(clip: Clip, f: number): Pose | null {
  const p = clip.path[f], yaw = clip.yaw_deg[f];
  if (!p || p[0] === null || p[1] === null || p[2] === null || yaw === null || yaw === undefined) return null;
  return { x: p[0], y: p[1], z: p[2], yawDeg: yaw };
}

/** Points of a depth cell in the camera's frame (x right, y down, z forward). NaN depth stays NaN. */
export function cellPoints(z: Float32Array, k: CellIntrinsics, w = GRID_W, h = GRID_H): Float32Array {
  const out = new Float32Array(z.length * 3);
  for (let v = 0; v < h; v++) for (let u = 0; u < w; u++) {
    const i = v * w + u, d = z[i];
    out[3 * i] = ((u - k.cx) / k.fx) * d;                   // pixel centres at integer coordinates, as the pipeline's intrinsics have them
    out[3 * i + 1] = ((v - k.cy) / k.fy) * d;
    out[3 * i + 2] = d;
  }
  return out;
}

/** Camera-frame points into the first camera's frame (the tank's), by the recovered position and yaw. */
export function placePoints(pts: Float32Array, pose: Pose): Float32Array {
  const th = (pose.yawDeg * Math.PI) / 180, c = Math.cos(th), s = Math.sin(th);
  const out = new Float32Array(pts.length);
  for (let i = 0; i < pts.length; i += 3) {
    const x = pts[i], y = pts[i + 1], z = pts[i + 2];
    out[i] = c * x + s * z + pose.x;
    out[i + 1] = y + pose.y;
    out[i + 2] = -s * x + c * z + pose.z;
  }
  return out;
}

/**
 * The gap at every vertex of the dream's surface, as the heat reads it: signed, positive where the dream is nearer than the real
 * tank along the same ray from the first camera (Zreal / Zdream - 1, the relative gap in inverse depth). NaN where the dream has no
 * depth, or the ray leaves the real tank's cell, or the real tank has no depth there (no real camera looked).
 */
export function gapField(world: Float32Array, tank: Float32Array, k: CellIntrinsics, w = GRID_W, h = GRID_H): Float32Array {
  const n = world.length / 3, out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const X = world[3 * i], Y = world[3 * i + 1], Z = world[3 * i + 2];
    if (!(Z > 1)) { out[i] = NaN; continue; }
    const u = Math.round((X / Z) * k.fx + k.cx), v = Math.round((Y / Z) * k.fy + k.cy);
    const zr = u >= 0 && u < w && v >= 0 && v < h ? tank[v * w + u] : NaN;
    out[i] = Number.isFinite(zr) ? zr / Z - 1 : NaN;
  }
  return out;
}

/** Triangle indices over a w x h grid of points: both triangles of a cell, only where every corner has depth and no depth jump. */
export function gridIndices(z: Float32Array, w = GRID_W, h = GRID_H, maxJump = MAX_JUMP): Uint32Array {
  const idx: number[] = [];
  const ok = (a: number, b: number, c: number) => {
    const za = z[a], zb = z[b], zc = z[c];
    if (!(za > 0 && zb > 0 && zc > 0)) return false;
    const lo = Math.min(za, zb, zc), hi = Math.max(za, zb, zc);
    return (hi - lo) / hi <= maxJump;
  };
  for (let v = 0; v + 1 < h; v++) for (let u = 0; u + 1 < w; u++) {
    const a = v * w + u, b = a + 1, c = a + w, d = c + 1;
    if (ok(a, b, c)) idx.push(a, c, b);
    if (ok(b, c, d)) idx.push(b, c, d);
  }
  return Uint32Array.from(idx);
}

/** Vertex colours (0..1 RGB) for the dream's surface from the gap, in the heat's own palette; no gap is the unseen grey. */
export function gapColours(gap: Float32Array, heat: HeatPalette): Float32Array {
  const out = new Float32Array(gap.length * 3);
  for (let i = 0; i < gap.length; i++) {
    const c = residualColour(heat, gap[i]) ?? heat.unseen_rgb;
    out[3 * i] = c[0] / 255; out[3 * i + 1] = c[1] / 255; out[3 * i + 2] = c[2] / 255;
  }
  return out;
}

/** World (x right, y down, z forward, su) to the viewer's scene (y up, the tank receding along -z, 100 su a unit). */
export function toScene(pts: Float32Array): Float32Array {
  const out = new Float32Array(pts.length);
  for (let i = 0; i < pts.length; i += 3) { out[i] = pts[i] / 100; out[i + 1] = -pts[i + 1] / 100; out[i + 2] = -pts[i + 2] / 100; }
  return out;
}
