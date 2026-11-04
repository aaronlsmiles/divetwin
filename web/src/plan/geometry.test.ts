import { describe, expect, it } from "vitest";
import { cursorAt, farWall, makeView, pathRuns, scaleTicks, TICK_GUTTER, VIEW, wallPoints } from "./geometry";
import { parseClips, parsePath, parsePlan } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";

const doc = parseClips(readFixtureJson("clips.json"));
const [dive, pellets, lost, calm] = doc.clips;
const pathOf = (c: typeof dive) => parsePath(readFixtureJson(c.assets.path), c);
const planOf = (c: typeof dive) => parsePlan(readFixtureJson(doc.recordings[c.recording_key].plan), c.recording_key);

describe("plan view geometry", () => {
  it("one scale for both axes, everything inside the square, forward up the page", () => {
    const plan = planOf(dive), v = makeView(plan, pathOf(dive));
    for (const [x, z] of plan.profile) {
      expect(v.x(x)).toBeGreaterThanOrEqual(0); expect(v.x(x)).toBeLessThanOrEqual(VIEW);
      expect(v.z(z)).toBeGreaterThanOrEqual(0); expect(v.z(z)).toBeLessThanOrEqual(VIEW);
    }
    expect(v.z(0)).toBeGreaterThan(v.z(plan.far_end));
    expect(v.x(10) - v.x(0)).toBeCloseTo(v.s * 10, 9);
    expect(v.z(0) - v.z(10)).toBeCloseTo(v.s * 10, 9);
  });
  it("draws the far wall at its measured distance, across the profile points that lie on it", () => {
    const plan = planOf(dive), w = farWall(plan);
    expect(w.z).toBe(plan.far_end);
    expect(w.x2).toBeGreaterThan(w.x1);
    for (const [x, z] of plan.profile) if (z >= 0.97 * plan.far_end) { expect(x).toBeGreaterThanOrEqual(w.x1); expect(x).toBeLessThanOrEqual(w.x2); }
  });
  it("the walls are a polyline of the whole profile", () => {
    const plan = planOf(dive);
    expect(wallPoints(plan, makeView(plan, pathOf(dive))).split(" ")).toHaveLength(plan.profile.length);
  });
  it("the path is gold exactly where D is above 3, and the runs join end to end", () => {
    const runs = pathRuns(pathOf(dive), dive);
    expect(runs.some((r) => r.gold)).toBe(true);
    const goldPts = runs.filter((r) => r.gold).reduce((n, r) => n + r.pts.length - 1, 0);
    expect(goldPts).toBe(dive.D.filter((d, i) => i > 0 && d! > 3).length);
    for (let i = 1; i < runs.length; i++) expect(runs[i].pts[0]).toEqual(runs[i - 1].pts[runs[i - 1].pts.length - 1]);
    expect(pathRuns(pathOf(calm), calm).some((r) => r.gold)).toBe(false);
  });
  it("a lost or capped path stops at its last trusted frame and is never extended", () => {
    for (const c of [pellets, lost]) {
      const p = pathOf(c), runs = pathRuns(p, c);
      const n = runs.reduce((k, r) => k + r.pts.length - 1, 0);
      expect(n).toBe(c.unverifiable_from! - 1);
    }
  });
  it("the cursor follows the frame, and freezes on the last trusted point past the end", () => {
    const p = pathOf(pellets), u = pellets.unverifiable_from!;
    expect(cursorAt(p, 5)).toMatchObject({ x: p.x[5], z: p.z[5], frozen: false });
    expect(cursorAt(p, u + 10)).toMatchObject({ x: p.x[u - 1], z: p.z[u - 1], frozen: true });
    expect(cursorAt(pathOf(dive), 120)!.frozen).toBe(false);
  });
  it("a clip unverifiable from frame 0 has no cursor and no stop marker (break-ui, task 4.6: path.x[-1] was NaN on the page)", () => {
    const p = { ...pathOf(dive), unverifiable_from: 0 };
    for (const f of [0, 1, 60, 120]) expect(cursorAt(p, f)).toBeNull();
    expect(cursorAt(p, -1)).toBeNull();
  });
  it("a path that backs out past the start (z below 0) stays inside the square, and the scale reaches below 0", () => {
    const plan = planOf(calm), p0 = pathOf(calm);
    const back = { ...p0, z: p0.z.map((z, i) => (z === null ? null : -2 * i)) };     // 240 su backwards by frame 120
    const v = makeView(plan, back);
    for (const z of back.z) if (z !== null) { expect(v.z(z)).toBeGreaterThanOrEqual(0); expect(v.z(z)).toBeLessThanOrEqual(VIEW); }
    expect(v.z(plan.far_end)).toBeGreaterThanOrEqual(0);
    expect(v.zMin).toBe(-240);
    expect(scaleTicks(v.zMax, v.zMin)).toEqual([-200, 0, 200, 400, 600, 800].filter((t) => t <= v.zMax));
  });
  it("leaves a gutter on the left for the scale's labels: nothing is drawn left of it", () => {
    const plan = planOf(dive), v = makeView(plan, pathOf(dive));
    for (const [x] of plan.profile) expect(v.x(x)).toBeGreaterThanOrEqual(TICK_GUTTER);
  });
  it("scale ticks every 200 su up to the far end", () => {
    expect(scaleTicks(837)).toEqual([0, 200, 400, 600, 800]);
  });
});
