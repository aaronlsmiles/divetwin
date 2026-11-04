import type { Clip, PathFile, PlanFile } from "../data/types";
import { D_THRESHOLD } from "../lib/series";

export const VIEW = 400, MARGIN = 28;                 // a square viewBox, as docs/DESIGN.md asks
export const TICK_GUTTER = 44;                        // the left edge is the scale's: its labels ("800", "−200") sit in it, unclipped

export interface View { s: number; x: (su: number) => number; z: (su: number) => number; xMin: number; xMax: number; zMin: number; zMax: number }

/** One uniform scale (px per su) for both axes: the drawing is true to shape, a long thin tank stays long and thin.
 *  Forward (z) runs up the page from the camera's start; a path that backs out past the start (z < 0) is drawn below it,
 *  never off the square. */
export function makeView(plan: PlanFile, path: PathFile): View {
  const xs = [...plan.profile.map((p) => p[0]), ...path.x.filter((v): v is number => v !== null)];
  const zs = [...plan.profile.map((p) => p[1]), ...path.z.filter((v): v is number => v !== null), plan.far_end, 0];
  const xMin = Math.min(...xs), xMax = Math.max(...xs), zMin = Math.min(...zs), zMax = Math.max(...zs);
  const w = VIEW - TICK_GUTTER - MARGIN;
  const s = Math.min(w / (xMax - xMin || 1), (VIEW - 2 * MARGIN) / (zMax - zMin || 1));
  const x0 = TICK_GUTTER + (w - s * (xMax - xMin)) / 2;
  return { s, xMin, xMax, zMin, zMax, x: (v) => x0 + s * (v - xMin), z: (v) => VIEW - MARGIN - s * (v - zMin) };
}

/** The measured walls: the profile as one polyline (the tank from above at mid-height). */
export const wallPoints = (plan: PlanFile, v: View): string => plan.profile.map(([x, z]) => `${v.x(x).toFixed(1)},${v.z(z).toFixed(1)}`).join(" ");

/** The far wall, drawn at its measured distance across the profile points that lie on it. */
export function farWall(plan: PlanFile): { x1: number; x2: number; z: number } {
  const on = plan.profile.filter(([, z]) => z >= 0.97 * plan.far_end).map(([x]) => x);
  return { x1: on.length ? Math.min(...on) : 0, x2: on.length ? Math.max(...on) : 0, z: plan.far_end };
}

export interface Run { gold: boolean; pts: [number, number][] }          // su coordinates [x, z]

/** The recovered path in runs, gold where D is above 3 (the segment into a frame takes that frame's D). Stops at the last trusted frame. */
export function pathRuns(path: PathFile, clip: Clip): Run[] {
  const runs: Run[] = [];
  for (let i = 1; i < path.x.length; i++) {
    const a = [path.x[i - 1], path.z[i - 1]], b = [path.x[i], path.z[i]];
    if (a[0] === null || a[1] === null || b[0] === null || b[1] === null) break;
    const gold = (clip.D[i] ?? 0) > D_THRESHOLD;
    const last = runs[runs.length - 1];
    if (last && last.gold === gold) last.pts.push([b[0], b[1]]);
    else runs.push({ gold, pts: [[a[0], a[1]], [b[0], b[1]]] });
  }
  return runs;
}

/** Where the cursor sits: the path at frame f, or the last trusted point once the frame is past it (never beyond). */
export function cursorAt(path: PathFile, f: number): { x: number; z: number; frozen: boolean; yaw: number } | null {
  const last = path.unverifiable_from === null ? path.x.length - 1 : path.unverifiable_from - 1;
  if (last < 0) return null;                                   // nothing was ever verified (unverifiable from frame 0): no point to draw, never path.x[-1]
  const i = Math.min(f, last);
  const x = path.x[i], z = path.z[i];
  if (x === null || z === null || x === undefined || z === undefined) return null;
  return { x, z, frozen: f > last, yaw: path.yaw_deg[i] ?? 0 };
}

/** Ticks every 200 su from the lowest multiple at or above zMin (0 unless the path backs out) up to zMax. */
export const scaleTicks = (zMax: number, zMin = 0, step = 200): number[] => {
  const lo = Math.ceil(zMin / step);
  return Array.from({ length: Math.floor(zMax / step) - lo + 1 }, (_, k) => (k + lo) * step);
};
