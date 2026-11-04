import { describe, expect, it } from "vitest";
import { D_AXIS_MIN, makeDTrack, makeTrack, pathD, splitAtThreshold, trustedSeries, yMaxFor } from "./curve";
import { parseClips } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";

const [dive, pellets, lost] = parseClips(readFixtureJson("clips.json")).clips;

describe("the D curve as geometry", () => {
  it("is ink up to 3 and gold above it, cut exactly where it crosses the line", () => {
    const segs = splitAtThreshold([1, 2, 4, 4, 2, 1], 3);
    expect(segs.map((s) => s.gold)).toEqual([false, true, false]);
    expect(segs[0].pts).toEqual([[0, 1], [1, 2], [1.5, 3]]);
    expect(segs[1].pts).toEqual([[1.5, 3], [2, 4], [3, 4], [3.5, 3]]);
    expect(segs[2].pts).toEqual([[3.5, 3], [4, 2], [5, 1]]);
  });
  it("exactly 3 is ink (gold means D above 3)", () => {
    const segs = splitAtThreshold([1, 3, 3, 1], 3);
    expect(segs.every((s) => !s.gold)).toBe(true);
  });
  it("a null breaks the line instead of joining across it", () => {
    const segs = splitAtThreshold([1, 2, null, 2, 1], 3);
    expect(segs.map((s) => s.pts)).toEqual([[[0, 1], [1, 2]], [[3, 2], [4, 1]]]);
  });
  it("a curve that never passes 3 has no gold at all", () => {
    expect(splitAtThreshold([0.5, 1, 2.9, 3, 1]).some((s) => s.gold)).toBe(false);
  });
  it("past where verification ran out there is no curve: pellets' D and V stop at the cap, whatever the file holds there", () => {
    const u = pellets.unverifiable_from!;
    const v = trustedSeries(pellets, pellets.verified);
    expect(pellets.verified[u]).toBe(0);
    expect(v[u]).toBeNull();
    expect(v[u - 1]).not.toBeNull();
    const segs = splitAtThreshold(trustedSeries(pellets, pellets.D));
    expect(Math.max(...segs.flatMap((s) => s.pts.map((p) => p[0])))).toBeLessThanOrEqual(u - 1);
    const l = splitAtThreshold(trustedSeries(lost, lost.D));
    expect(Math.max(...l.flatMap((s) => s.pts.map((p) => p[0])))).toBeLessThanOrEqual(lost.lost_from! - 1);
  });
  it("the default clip has gold from its crossing on, and the crossing is before its departure frame", () => {
    const segs = splitAtThreshold(trustedSeries(dive, dive.D));
    const gold = segs.filter((s) => s.gold);
    expect(gold.length).toBeGreaterThan(0);
    expect(gold[0].pts[0][1]).toBe(3);
    expect(gold[0].pts[0][0]).toBeLessThanOrEqual(dive.first_D3!);
  });
});

describe("axis and scales", () => {
  it("the D axis always has room above the 3 line, and is capped so one wild clip cannot flatten the rest", () => {
    expect(yMaxFor([0.9, 1.2])).toBe(4);
    expect(yMaxFor([1, 5.37, null])).toBe(6);
    expect(yMaxFor([1, 57])).toBe(8);
    expect(yMaxFor([null])).toBe(4);
  });
  it("maps frame 0 and the last frame to the edges and a value above the cap to the top", () => {
    const t = makeTrack(121, 600, 40, 4, 2);
    expect(t.x(0)).toBe(0);
    expect(t.x(120)).toBe(600);
    expect(t.y(0)).toBe(38);
    expect(t.y(4)).toBe(2);
    expect(t.y(99)).toBe(2);
    expect(t.y(3)).toBeLessThan(t.y(1));
  });
  it("draws a segment as an SVG path", () => {
    const t = makeTrack(11, 100, 22, 4, 1);
    expect(pathD(t, { gold: false, pts: [[0, 0], [5, 2], [10, 4]] })).toBe("M0,21L50,11L100,1");
  });
});

describe("the D track's piecewise scale (task 4.6)", () => {
  it("runs from 0.5 at the bottom edge to the axis top, with the 3 line between and the 1 line below it", () => {
    for (const yMax of [4, 6, 8]) {
      const t = makeDTrack(121, 600, 48, yMax);
      expect(t.y(D_AXIS_MIN)).toBe(46);
      expect(t.y(yMax)).toBe(2);
      expect(t.y(0.1)).toBe(46);                       // below the axis: drawn on the bottom edge
      expect(t.y(99)).toBe(2);                         // past the top: on the top edge
      expect(t.y(1)).toBeGreaterThan(t.y(3));
      expect(t.y(3)).toBeGreaterThan(t.y(yMax));
    }
  });
  it("gives 1 to 3 at least 20 px of the 48 px track on a clip that flares to 6, and more on a calm clip (it was 15 px)", () => {
    const flare = makeDTrack(121, 600, 48, 6), calm = makeDTrack(121, 600, 48, 4);
    expect(flare.y(1) - flare.y(3)).toBeGreaterThanOrEqual(20);
    expect(calm.y(1) - calm.y(3)).toBeGreaterThan(flare.y(1) - flare.y(3));
    const old = makeTrack(121, 600, 48, 6);
    expect(old.y(1) - old.y(3)).toBeLessThan(16);
  });
  it("above 3 the scale runs at half the pixels per unit, so a gold excursion is still drawn, only shorter", () => {
    const t = makeDTrack(121, 600, 48, 6);
    const below = (t.y(1) - t.y(3)) / 2, above = (t.y(3) - t.y(6)) / 3;
    expect(above / below).toBeCloseTo(0.5, 5);
    expect(t.y(3) - t.y(5.37)).toBeGreaterThan(10);
  });
  it("is monotone, so the curve never doubles back on itself", () => {
    const t = makeDTrack(121, 600, 48, 8);
    let last = Infinity;
    for (let v = 0; v <= 9; v += 0.05) { const y = t.y(v); expect(y).toBeLessThanOrEqual(last + 1e-9); last = y; }
  });
});
