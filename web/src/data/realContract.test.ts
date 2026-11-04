// The contract test against the real runs/assets (about 250 MB, gitignored): skipped when it is not there, run in the scratch
// layout and on Aaron's machine. It is what makes "the page reads the real file" true; the fixture tests only prove the code.
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseClips, parsePath, parsePlan } from "./load";
import { atlasCell, decodePng16, singleCell } from "./png16";
import { finding } from "../lib/finding";
import { dAt, firstSustained, secondsCell, vAt } from "../lib/series";

const ASSETS = process.env.DIVETWIN_ASSETS ?? join(dirname(fileURLToPath(import.meta.url)), "../../../runs/assets");
const have = existsSync(join(ASSETS, "clips.json"));
const json = (rel: string) => JSON.parse(readFileSync(join(ASSETS, rel), "utf8"));

describe.skipIf(!have)("the real runs/assets/clips.json", () => {
  const doc = have ? parseClips(json("clips.json")) : (undefined as never);

  it("parses: 35 clips, 5 recordings, every key the page reads", () => {
    expect(doc.clips).toHaveLength(35);
    expect(Object.keys(doc.recordings)).toHaveLength(5);
  });

  it("first_D3 is what D says, on all 35 clips (the page and the pipeline agree on the departure)", () => {
    for (const c of doc.clips) expect(firstSustained(c.D), c.clip).toBe(c.first_D3);
  });

  it("D_at and V_at agree with D and V at their frames wherever the frame is trusted", () => {
    for (const c of doc.clips) for (const key of ["0", "1", "2.5", "5", "10"]) {
      const f = Math.round(Number(key) * c.fps);
      if (f > c.n_frames - 1) continue;
      const d = secondsCell(c, key, "D"), v = secondsCell(c, key, "V");
      if (d.kind === "value") expect(d.value, `${c.clip} D@${key}`).toBeCloseTo(c.D[f]!, 2);
      if (v.kind === "value") expect(v.value, `${c.clip} V@${key}`).toBeCloseTo(c.verified[f]!, 3);
    }
  });

  it("no finding line and no reading ever shows NaN, undefined, null or a V of 0.00 past a cap", () => {
    for (const c of doc.clips) {
      expect(finding(c), c.clip).not.toMatch(/NaN|undefined|null/);
      if (c.unverifiable_from !== null) {
        for (const f of [c.unverifiable_from, c.n_frames - 1]) {
          expect(vAt(c, f).kind, `${c.clip} f${f}`).toBe("unverifiable");
          expect(dAt(c, f).kind).toBe("unverifiable");
        }
      }
    }
  });

  it("every clip's path.json and every recording's plan.json parse and agree with clips.json", () => {
    for (const c of doc.clips) expect(parsePath(json(c.assets.path), c).trusted_frames, c.clip).toBe(c.trusted_frames);
    for (const [k, r] of Object.entries(doc.recordings)) expect(parsePlan(json(r.plan), k).far_end).toBeCloseTo(r.far_end, 3);
  });

  it("the pellets Gen-4.5 clips are the four that run out, all 'travel cap', and the trusted travel is 100 su on every one", () => {
    const capped = doc.clips.filter((c) => c.unverifiable_reason === "travel cap");
    expect(capped.length).toBeGreaterThan(0);
    for (const c of capped) { expect(c.condition).toBe("saltwater-pellets"); expect(c.trusted_travel_su).toBe(100); }
  });

  it("a real relief atlas decodes to the size its metadata gives, and the cells hold depth", () => {
    const c = doc.clips.find((x) => x.seconds === 10)!;
    const atlas = decodePng16(readFileSync(join(ASSETS, c.assets.relief)));
    expect([atlas.width, atlas.height]).toEqual([c.relief.cols * c.relief.cell[0], c.relief.rows * c.relief.cell[1]]);
    const last = atlasCell(atlas, { cols: c.relief.cols, cell: c.relief.cell, depth_scale: c.relief.depth_scale }, c.n_frames - 1);
    expect(last.filter(Number.isFinite).length).toBeGreaterThan(last.length / 2);
    const tank = singleCell(decodePng16(readFileSync(join(ASSETS, c.assets.tank_relief))), c.relief.depth_scale);
    expect(tank).toHaveLength(c.relief.cell[0] * c.relief.cell[1]);
  });

  it("the heat block carries the floor map's ramp and its words, and every recording has its preview", () => {
    expect(doc.heat.floor_ramp).toHaveLength(3);
    expect(doc.heat.floor_means).toBe("where mono depth already errs on the real tank; display only, the same for every frame");
    for (const r of Object.values(doc.recordings)) expect(existsSync(join(ASSETS, r.floor_map.preview)), r.floor_map.preview).toBe(true);
  });

  it("V at the departure of saltwater Wan B (f102) and Wan N (f97) is below one and says 'unseen, or covered by a tracked moving object'", () => {
    for (const [id, f] of [["saltwater__wan22__B__5s", 102], ["saltwater__wan22__N__5s", 97]] as const) {
      const c = doc.clips.find((x) => x.clip === id)!;
      expect(c.first_D3, id).toBe(f);
      expect(c.verified[f]!, id).toBeLessThan(0.995);
      expect(c.moving_track[f], id).toBe(true);
      expect(finding(c), id).toContain("part of the frame is unseen, or covered by a tracked moving object");
    }
  });
});
