// The findings band's tally (hub call 92): the counts are the finding line's own classification, so a count and a finding line can never
// disagree. Held on the four-clip fixture, on the worst cases, and on the real runs/assets/clips.json when it is there.
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { Clip } from "../data/types";
import { parseClips } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";
import { finding, findingKind, type FindingKind } from "./finding";
import { steadyV, tally, TALLY_ORDER, tallyWords } from "./tally";
import { fmtV } from "./format";
import { framesAbove } from "./series";
import { bandFigures } from "../test/facts";

const fixture = parseClips(readFixtureJson("clips.json"));
const [dive, pellets, lost, calm] = fixture.clips;

/** The finding line's four forms, read from the words it prints: what a reader sees under the title. */
const FORM: Record<FindingKind, RegExp> = {
  departs: /^D passes 3 at frame \d+/,
  spikes: /^D tops 3 on \d+ frames? but never holds it for 12/,
  under: /^D stays under 3; peak/,
  unchecked: /^(Verification ran out at frame \d+|No frame could be measured)/,
};

const formOf = (c: Clip): FindingKind[] => (Object.keys(FORM) as FindingKind[]).filter((k) => FORM[k].test(finding(c)));

/** Clips made from the fixture's, one per form the fixture lacks, so every branch is held. */
const spike: Clip = { ...calm, clip: "spike", D: calm.D.map((d, i) => (i >= 40 && i < 43 ? 3.14 : d)), first_D3: null };
const none: Clip = { ...calm, clip: "none", D: calm.D.map(() => null) };
const departsThenLost: Clip = { ...dive, clip: "departs-lost", unverifiable_from: 100, unverifiable_reason: "path lost" };
const spikeThenCapped: Clip = { ...spike, clip: "spike-capped", unverifiable_from: 60, unverifiable_reason: "travel cap" };
const lostAtZero: Clip = { ...calm, clip: "lost-0", unverifiable_from: 0, unverifiable_reason: "path lost" };
const made = [spike, none, departsThenLost, spikeThenCapped, lostAtZero];

describe("findingKind is the finding line's classification", () => {
  it("every clip has exactly one form, and it is the kind", () => {
    for (const c of [...fixture.clips, ...made]) {
      expect(formOf(c), `${c.clip}: ${finding(c)}`).toEqual([findingKind(c)]);
    }
  });
  it("the fixture's four clips, and the made ones", () => {
    expect([dive, pellets, lost, calm].map(findingKind)).toEqual(["departs", "unchecked", "unchecked", "under"]);
    expect(made.map(findingKind)).toEqual(["spikes", "unchecked", "departs", "spikes", "unchecked"]);
  });
  it("a departure that later runs out still counts as a departure, as its finding line leads with it", () => {
    expect(finding(departsThenLost)).toMatch(/^D passes 3 .*; verification ran out at frame 100/);
    expect(findingKind(departsThenLost)).toBe("departs");
  });
});

describe("the tally", () => {
  it("counts each kind once, in the band's order, and leaves out a kind no clip has", () => {
    const t = tally(fixture.clips);
    expect(TALLY_ORDER).toEqual(["departs", "spikes", "under", "unchecked"]);
    expect(t.map((g) => [g.kind, g.n])).toEqual([["departs", 1], ["under", 1], ["unchecked", 2]]);
    for (const g of t) expect(g.clips.map((c) => c.clip)).toEqual(fixture.clips.filter((c) => findingKind(c) === g.kind).map((c) => c.clip));
  });
  it("adds up to every clip, and each group is the clips whose finding line has that form", () => {
    const clips = [...fixture.clips, ...made];
    const t = tally(clips);
    expect(t.reduce((n, g) => n + g.n, 0)).toBe(clips.length);
    for (const g of t) for (const c of g.clips) expect(formOf(c)).toEqual([g.kind]);
  });
  it("says each group in words, with the verb agreeing with the count", () => {
    expect(tallyWords("departs", 3)).toBe("leave the tank for good");
    expect(tallyWords("departs", 1)).toBe("leaves the tank for good");
    expect(tallyWords("spikes", 2)).toBe("spike past 3");
    expect(tallyWords("spikes", 1)).toBe("spikes past 3");
    expect(tallyWords("under", 25)).toBe("stay under 3");
    expect(tallyWords("under", 1)).toBe("stays under 3");
    expect(tallyWords("unchecked", 5)).toBe("can't be checked to the end");
    expect(tallyWords("unchecked", 1)).toBe("can't be checked to the end");
  });
  it("an empty set gives an empty tally", () => {
    expect(tally([])).toEqual([]);
  });
});

describe("steadyV: the engine whose clips past 3 all keep V at 1.00", () => {
  it("on the fixture it is Gen-4.5, from the departing clip's own V", () => {
    const s = steadyV(fixture.clips)!;
    expect(s.engine).toBe("gen45");
    expect(fmtV(s.v)).toBe("1.00");
    expect(s.v).toBe(Math.min(...dive.verified.filter((v): v is number => v !== null)));
  });
  it("is nothing when a clip past 3 lets V fall, or when no clip passes 3", () => {
    const fallen = { ...dive, verified: dive.verified.map((v, i) => (i === 100 ? 0.8 : v)) };
    expect(steadyV([fallen, calm])).toBeNull();
    expect(steadyV([calm, pellets])).toBeNull();
  });
  it("is nothing when the steady clips only spike: the line speaks of a dream leaving", () => {
    expect(steadyV([spike, calm])).toBeNull();
  });
});

const ASSETS = process.env.DIVETWIN_ASSETS ?? join(dirname(fileURLToPath(import.meta.url)), "../../../runs/assets");
const have = existsSync(join(ASSETS, "clips.json"));

describe.skipIf(!have)("on the real runs/assets/clips.json", () => {
  const doc = have ? parseClips(JSON.parse(readFileSync(join(ASSETS, "clips.json"), "utf8"))) : (undefined as never);
  it("every one of the 35 clips' finding lines has the form its kind says", () => {
    for (const c of doc.clips) expect(formOf(c), `${c.clip}: ${finding(c)}`).toEqual([findingKind(c)]);
  });
  it("the tally is THESIS.md's: 3 leave for good, 2 spike past 3, 25 stay under 3, 5 run out first", () => {
    expect(tally(doc.clips).map((g) => [g.kind, g.n])).toEqual([["departs", 3], ["spikes", 2], ["under", 25], ["unchecked", 5]]);
    expect(bandFigures(doc).slice(0, 4), "the facts file's own count agrees").toEqual(["3", "2", "5", "25"]);
    const ids = (k: FindingKind) => tally(doc.clips).find((g) => g.kind === k)!.clips.map((c) => c.clip).sort();
    expect(ids("departs")).toEqual(["freshwater-basicEnhance__gen45__N__5s", "saltwater__wan22__B__5s", "saltwater__wan22__N__5s"]);
    expect(ids("spikes")).toEqual(["air__wan22__B__5s", "saltwater__gen45__N__5s"]);
    expect(ids("unchecked")).toEqual(["air__wan22__N__5s", "saltwater-pellets__gen45__B__5s", "saltwater-pellets__gen45__D__10s",
      "saltwater-pellets__gen45__D__5s", "saltwater-pellets__gen45__N__5s"]);
  });
  it("the second surprise holds: both Gen-4.5 clips past 3 keep V at 1.00 on every measured frame; the Wan ones past 3 do not", () => {
    const s = steadyV(doc.clips)!;
    expect(s.engine).toBe("gen45");
    expect(fmtV(s.v)).toBe("1.00");
    const past = doc.clips.filter((c) => framesAbove(c) > 0);
    expect(past.filter((c) => c.engine === "gen45").map((c) => c.clip).sort()).toEqual(["freshwater-basicEnhance__gen45__N__5s", "saltwater__gen45__N__5s"]);
    for (const c of past.filter((x) => x.engine === "wan22")) expect(Math.min(...c.verified.filter((v): v is number => v !== null)), c.clip).toBeLessThan(0.995);
  });
});
