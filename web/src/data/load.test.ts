import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearCache, DataError, loadClips, loadPath, loadPlan, parseClips, parsePath, parsePlan } from "./load";
import { FIXTURE_IDS, readFixtureJson, stubFixtureFetch } from "../test/fixtureMedia";

beforeEach(() => clearCache());
afterEach(() => vi.unstubAllGlobals());

describe("clips.json", () => {
  it("parses the fixture: four real clips, their three recordings, the palette", () => {
    const doc = parseClips(readFixtureJson("clips.json"));
    expect(doc.clips.map((c) => c.clip)).toEqual([...FIXTURE_IDS]);
    expect(Object.keys(doc.recordings).sort()).toEqual(["air", "freshwater-basicEnhance", "saltwater-pellets"]);
    expect(doc.heat.positive).toHaveLength(3);
    expect(doc.unit).toContain("su");
  });

  it("refuses a file that is not this contract's version or unit", () => {
    const doc = readFixtureJson("clips.json");
    expect(() => parseClips({ ...doc, version: "v2" })).toThrow(DataError);
    expect(() => parseClips({ ...doc, unit: "mm" })).toThrow(/unit/);
    expect(() => parseClips(null)).toThrow(DataError);
  });

  it("names the clip and the key when a key is missing (never a silent undefined on the page)", () => {
    const doc = readFixtureJson("clips.json");
    delete doc.clips[1].unverifiable_from;
    expect(() => parseClips(doc)).toThrow(/saltwater-pellets__gen45__N__5s.*unverifiable_from/);
    const doc2 = readFixtureJson("clips.json");
    delete doc2.heat.unverified_hatch;
    expect(() => parseClips(doc2)).toThrow(/heat.*unverified_hatch/);
    const doc3 = readFixtureJson("clips.json");
    delete doc3.heat.floor_ramp;
    expect(() => parseClips(doc3)).toThrow(/heat.*floor_ramp/);
    const doc4 = readFixtureJson("clips.json");
    doc4.heat.floor_ramp = [[0, [1, 2, 3]]];
    expect(() => parseClips(doc4)).toThrow(/floor_ramp.*two stops/);
  });

  it("checks that every per-frame array has n_frames entries", () => {
    const doc = readFixtureJson("clips.json");
    doc.clips[0].D = doc.clips[0].D.slice(1);
    expect(() => parseClips(doc)).toThrow(/freshwater-basicEnhance__gen45__N__5s.*D.*120.*121/);
  });

  it("checks that every clip's recording is in the file", () => {
    const doc = readFixtureJson("clips.json");
    delete doc.recordings["air"];
    expect(() => parseClips(doc)).toThrow(/recording.*air/);
  });

  it("keeps the pellets traps as the data has them: V is 0.0 past the cap, D and path are null", () => {
    const pellets = parseClips(readFixtureJson("clips.json")).clips[1];
    expect(pellets.unverifiable_reason).toBe("travel cap");
    expect(pellets.verified[pellets.unverifiable_from!]).toBe(0);
    expect(pellets.D[pellets.unverifiable_from!]).toBeNull();
    expect(pellets.path[pellets.unverifiable_from!]).toEqual([null, null, null]);
  });
});

describe("path.json and plan.json", () => {
  it("parse the fixtures and agree with clips.json", () => {
    const doc = parseClips(readFixtureJson("clips.json"));
    for (const c of doc.clips) {
      const p = parsePath(readFixtureJson(c.assets.path), c);
      expect(p.x).toHaveLength(c.n_frames);
      expect(p.unverifiable_from).toBe(c.unverifiable_from);
    }
    const plan = parsePlan(readFixtureJson(doc.recordings["air"].plan), "air");
    expect(plan.profile.length).toBeGreaterThan(50);
    expect(plan.far_end).toBe(doc.recordings["air"].far_end);
  });

  it("refuses a path that disagrees with its clip", () => {
    const doc = parseClips(readFixtureJson("clips.json"));
    const bad = readFixtureJson(doc.clips[0].assets.path);
    bad.clip = "someone-else";
    expect(() => parsePath(bad, doc.clips[0])).toThrow(/someone-else/);
    const short = readFixtureJson(doc.clips[0].assets.path);
    short.x = short.x.slice(5);
    expect(() => parsePath(short, doc.clips[0])).toThrow(/x/);
  });

  it("refuses a plan in other units", () => {
    const plan = readFixtureJson("recordings/air/plan.json");
    expect(() => parsePlan({ ...plan, unit: "mm" }, "air")).toThrow(/unit/);
    expect(() => parsePlan({ ...plan, profile: [[1, 2, 3]] }, "air")).toThrow(/profile/);
  });
});

describe("fetching", () => {
  it("loads clips.json, then a clip's path and its recording's plan, from the media base", async () => {
    const asked = stubFixtureFetch("/media/");
    const doc = await loadClips("/media/");
    const path = await loadPath(doc.clips[0], "/media/");
    const plan = await loadPlan(doc.recordings[doc.clips[0].recording_key], doc.clips[0].recording_key, "/media/");
    expect(path.clip).toBe(doc.clips[0].clip);
    expect(plan.condition).toBe("freshwater-basicEnhance");
    expect(asked).toEqual(["/media/clips.json", `/media/${doc.clips[0].assets.path}`, `/media/${doc.recordings["freshwater-basicEnhance"].plan}`]);
  });

  it("asks once for a file it already has", async () => {
    const asked = stubFixtureFetch("/media/");
    await loadClips("/media/");
    await loadClips("/media/");
    expect(asked).toHaveLength(1);
  });

  it("a missing file is a DataError that names the URL, and is not cached as a success", async () => {
    stubFixtureFetch("/media/");
    await expect(loadClips("/other/")).rejects.toThrow(/\/other\/clips.json.*404/);
    await expect(loadClips("/other/")).rejects.toThrow(DataError);
  });

  it("an answer that is 200 but not JSON (a dev server's home page for a missing file) is a DataError that names the URL", async () => {
    vi.stubGlobal("fetch", async () => new Response("<!doctype html><title>Dive Twin</title>", { status: 200, headers: { "content-type": "text/html" } }));
    await expect(loadClips("/media/")).rejects.toThrow(/\/media\/clips.json: the answer is not JSON/);
    await expect(loadClips("/media/")).rejects.toThrow(DataError);
  });

  it("with no media base, says so instead of asking a made-up host", async () => {
    await expect(loadClips("")).rejects.toThrow(/VITE_MEDIA_BASE/);
  });
});
