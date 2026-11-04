import { describe, expect, it } from "vitest";
import { cellIntrinsics, cellPoints, fallbackIntrinsics, gapColours, gapField, gridIndices, placePoints, poseAt, REAL_INTRINSICS, toScene } from "./surfaces";
import { parseClips } from "../data/load";
import { residualColour } from "../lib/palette";
import { readFixtureJson } from "../test/fixtureMedia";

const doc = parseClips(readFixtureJson("clips.json"));
const [dive, pellets] = doc.clips;
const W = 160, H = 90;
const flat = (z: number) => new Float32Array(W * H).fill(z);
const k = cellIntrinsics(dive);
const FILL: [number, number, number, number] = [0, 0, 2208, 1242];

describe("relief surfaces", () => {
  it("the fallback is the pipeline's calibration, pinned: fx 1433.347, and a principal point that is NOT the frame's centre", () => {
    expect(REAL_INTRINSICS).toEqual({ fx: 1433.347, cx: 1156.798, cy: 631.871 });
    const f = fallbackIntrinsics(FILL);
    expect(f.fx).toBeCloseTo((1433.347 * 160) / 2208, 9);
    expect(f.fy).toBeCloseTo((1433.347 * 90) / 1242, 9);
    expect(f.cx).toBeGreaterThan(83);                       // 52 px right of the real frame's centre: not 80
    expect(Math.abs(f.cx - 80)).toBeGreaterThan(3);
  });
  it("a box with a vertical offset moves the principal point as the pipeline's box_intrinsics does", () => {
    const cover = fallbackIntrinsics([0, 13.8, 2208, 1214.4]);
    const fill = fallbackIntrinsics(FILL);
    expect(cover.fy).toBeGreaterThan(fill.fy);
    expect(cover.cy).toBeCloseTo(((631.871 + 0.5 - 13.8) * 90) / 1214.4 - 0.5, 9);       // mapping.box_intrinsics: (cy + 0.5 - y0) * sy - 0.5
    expect(cover.cy).not.toBe(fill.cy);
  });
  it("the clip's own intrinsics win; a clip without them (an older file) falls back", () => {
    expect(k).toEqual({ fx: dive.relief.fx, fy: dive.relief.fy, cx: dive.relief.cx, cy: dive.relief.cy });
    const old = { ...dive, relief: { ...dive.relief, fx: undefined, fy: undefined, cx: undefined, cy: undefined } };
    expect(cellIntrinsics(old)).toEqual(fallbackIntrinsics(dive.relief.box));
  });
  it("back-projects a flat wall: depth is z, and the principal point's ray is on the axis", () => {
    const p = cellPoints(flat(500), { fx: 100, fy: 100, cx: 83, cy: 45 });
    expect(p[3 * (45 * W + 83) + 2]).toBe(500);
    expect(p[3 * (45 * W + 83)]).toBe(0);
    expect(p[3 * (45 * W + 93)]).toBeCloseTo(50, 3);        // ten cells right of the principal point, at 500 su, 100 px focal
  });
  it("a dream that moved forward and sees a wall nearer by the same amount agrees with the tank: gap 0", () => {
    const tank = flat(500);
    const world = placePoints(cellPoints(flat(400), k), { x: 0, y: 0, z: 100, yawDeg: 0 });
    const gap = gapField(world, tank, k);
    expect(Math.max(...Array.from(gap).map(Math.abs))).toBeLessThan(1e-4);
  });
  it("a dream surface nearer than the tank reads positive (warm), farther reads negative (blue): the heat's own sign", () => {
    const tank = flat(500);
    const near = gapField(placePoints(cellPoints(flat(300), k), { x: 0, y: 0, z: 100, yawDeg: 0 }), tank, k);
    const far = gapField(placePoints(cellPoints(flat(600), k), { x: 0, y: 0, z: 100, yawDeg: 0 }), tank, k);
    expect(near[45 * W + 80]).toBeCloseTo(500 / 400 - 1, 5);
    expect(far[45 * W + 80]).toBeCloseTo(500 / 700 - 1, 5);
    const heat = doc.heat;
    expect(residualColour(heat, near[45 * W + 80])).toEqual(residualColour(heat, 0.25));
    expect(far[45 * W + 80]).toBeLessThan(0);
  });
  it("yaw moves where the surface lands: a surface yawed 20 degrees leaves the tank's cell at the edge (no gap), the centre does not", () => {
    const world = placePoints(cellPoints(flat(400), k), { x: 0, y: 0, z: 0, yawDeg: 20 });
    const gap = gapField(world, flat(500), k);
    expect(Number.isNaN(gap[45 * W + 159])).toBe(true);
    expect(Number.isFinite(gap[45 * W + 80])).toBe(true);
  });
  it("no depth on either side is no gap, never zero", () => {
    const tank = flat(500); tank[10] = NaN;
    const dream = flat(400); dream[11] = NaN;
    const gap = gapField(placePoints(cellPoints(dream, k), { x: 0, y: 0, z: 0, yawDeg: 0 }), tank, k);
    expect(Number.isNaN(gap[11])).toBe(true);
    expect(Number.isNaN(gap[10])).toBe(true);
    expect(Number.isFinite(gap[12])).toBe(true);
  });
  it("triangles only where there is depth and no jump", () => {
    const z = flat(500);
    expect(gridIndices(z).length).toBe(6 * (W - 1) * (H - 1));
    z[100] = NaN;
    expect(gridIndices(z).length).toBeLessThan(6 * (W - 1) * (H - 1));
    const z2 = flat(500); z2[5 * W + 5] = 900;                       // a spike: its triangles are dropped, not stretched
    expect(gridIndices(z2).length).toBe(6 * (W - 1) * (H - 1) - 6 * 3);
  });
  it("colours are the heat's palette; no gap is the unseen grey", () => {
    const c = gapColours(Float32Array.from([0.25, Number.NaN]), doc.heat);
    const warm = residualColour(doc.heat, 0.25)!;
    expect(Array.from(c.slice(0, 3))).toEqual(warm.map((v) => v / 255).map((v) => Math.fround(v)));
    expect(c[3]).toBeCloseTo(doc.heat.unseen_rgb[0] / 255, 6);
  });
  it("the pose comes from the clip's path and yaw, and is null where the path is not drawn", () => {
    expect(poseAt(dive, 88)).toEqual({ x: dive.path[88][0], y: dive.path[88][1], z: dive.path[88][2], yawDeg: dive.yaw_deg[88] });
    expect(poseAt(pellets, pellets.unverifiable_from!)).toBeNull();
  });
  it("the scene is y up with the tank receding along -z, 100 su a unit", () => {
    expect(Array.from(toScene(Float32Array.from([100, 200, 300])))).toEqual([1, -2, -3]);
  });
});
