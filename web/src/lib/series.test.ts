import { describe, expect, it } from "vitest";
import { D_RUN, D_THRESHOLD, dAt, firstSustained, forwardAt, isUnverifiable, peakD, secondsCell, vAt } from "./series";
import { parseClips } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";

const [dive, pellets, lost, calm] = parseClips(readFixtureJson("clips.json")).clips;

describe("per-frame readings", () => {
  it("a trusted frame reads its values", () => {
    expect(dAt(dive, 88)).toEqual({ kind: "value", value: dive.D[88] });
    expect(vAt(dive, 88)).toEqual({ kind: "value", value: dive.verified[88] });
    expect(forwardAt(dive, 88)).toEqual({ kind: "value", value: dive.path[88][2] });
  });

  it("past the travel cap, V is unverifiable and never the 0.0 the pipeline wrote there", () => {
    const u = pellets.unverifiable_from!;
    expect(pellets.verified[u]).toBe(0);
    for (const f of [u, u + 1, pellets.n_frames - 1]) {
      expect(isUnverifiable(pellets, f)).toBe(true);
      expect(vAt(pellets, f)).toEqual({ kind: "unverifiable", reason: "travel cap" });
      expect(dAt(pellets, f).kind).toBe("unverifiable");
      expect(forwardAt(pellets, f).kind).toBe("unverifiable");
    }
    expect(isUnverifiable(pellets, u - 1)).toBe(false);
    expect(vAt(pellets, u - 1).kind).toBe("value");
  });

  it("a lost path is unverifiable from lost_from on, with its own reason", () => {
    expect(lost.lost_from).toBe(lost.unverifiable_from);
    expect(dAt(lost, lost.lost_from! - 1).kind).toBe("value");
    expect(dAt(lost, lost.lost_from!)).toEqual({ kind: "unverifiable", reason: "path lost" });
  });

  it("a clip that is never unverifiable never says so", () => {
    expect(calm.unverifiable_from).toBeNull();
    expect(Array.from({ length: calm.n_frames }, (_, f) => isUnverifiable(calm, f)).some(Boolean)).toBe(false);
  });

  it("a null in a trusted frame is 'none', not a number", () => {
    const c = { ...calm, D: calm.D.map((d, i) => (i === 5 ? null : d)) };
    expect(dAt(c, 5)).toEqual({ kind: "none" });
  });
});

describe("the departure test, re-derived from D", () => {
  it("is D above 3 for 12 frames in a row (pipeline/metrics.py), and a null breaks a run", () => {
    expect([D_THRESHOLD, D_RUN]).toEqual([3, 12]);
    const run = (n: number) => Array.from({ length: n }, () => 3.5);
    expect(firstSustained([1, 1, ...run(12), 1])).toBe(2);
    expect(firstSustained([1, ...run(11), 1])).toBeNull();
    expect(firstSustained([...run(6), null, ...run(6)])).toBeNull();
    expect(firstSustained([3, 3, 3, ...run(12)])).toBe(3);              // exactly 3 is not above 3
  });
  it("reproduces first_D3 on every fixture clip", () => {
    for (const c of [dive, pellets, lost, calm]) expect(firstSustained(c.D)).toBe(c.first_D3);
  });
});

describe("peak D", () => {
  it("is the largest D on the trusted frames, and its frame", () => {
    const p = peakD(dive)!;
    expect(p.value).toBe(Math.max(...dive.D.filter((d): d is number => d !== null)));
    expect(dive.D[p.frame]).toBe(p.value);
    expect(peakD({ ...calm, D: calm.D.map(() => null) })).toBeNull();
  });
});

describe("table cells at 0, 1, 2.5, 5 and 10 s", () => {
  it("D_at agrees with D at the frame it names, for every key that exists (the contract holds)", () => {
    for (const c of [dive, calm]) {
      for (const key of ["0", "1", "2.5", "5"]) {
        const f = Math.round(Number(key) * c.fps);
        const cell = secondsCell(c, key, "D");
        expect(cell.kind).toBe("value");
        expect((cell as { value: number }).value).toBeCloseTo(c.D[f]!, 2);
        expect((secondsCell(c, key, "V") as { value: number }).value).toBeCloseTo(c.verified[f]!, 3);
      }
    }
  });
  it("is none where the clip is shorter (10 s on a 5 s clip)", () => {
    expect(secondsCell(dive, "10", "D")).toEqual({ kind: "none" });
  });
  it("past the cap it says unverifiable for V as well as D: the data holds V_at['5'] = 0.0 there", () => {
    expect(pellets.V_at["5"]).toBe(0);
    expect(secondsCell(pellets, "5", "V")).toEqual({ kind: "unverifiable", reason: "travel cap" });
    expect(secondsCell(pellets, "5", "D").kind).toBe("unverifiable");
    expect(secondsCell(pellets, "0", "V").kind).toBe("value");
  });
});
