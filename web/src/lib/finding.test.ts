import { describe, expect, it } from "vitest";
import { cellText, fmtD, fmtPercent, fmtSu, fmtV, reasonText, UNVERIFIABLE, DASH } from "./format";
import { clipTitle, finding, findingFrame } from "./finding";
import { parseClips } from "../data/load";
import { dAt, secondsCell } from "./series";
import { readFixtureJson } from "../test/fixtureMedia";

const [dive, pellets, lost, calm] = parseClips(readFixtureJson("clips.json")).clips;
const numbers = (c: typeof dive) => c.D.filter((d): d is number => d !== null);

describe("formatting", () => {
  it("D never contradicts the gold: 3.004 reads 3.01 (above) and 2.996 reads 2.99 (not above)", () => {
    expect(fmtD(3.004)).toBe("3.01");
    expect(fmtD(2.996)).toBe("2.99");
    expect(fmtD(3)).toBe("3.00");
    expect(fmtD(3.025)).toBe("3.02");
    expect(fmtD(0.9)).toBe("0.90");
  });
  it("V, distance and share", () => {
    expect(fmtV(0.99976)).toBe("1.00");
    expect(fmtSu(711.09)).toBe("711");
    expect(fmtSu(-231.4)).toBe("\u2212231");                     // a true minus, never a hyphen
    expect(fmtSu(-0.2)).toBe("0");
    expect(fmtPercent(0.1335)).toBe("13 %");
  });
  it("a cell is a number, the word 'unverifiable', or a grey dash", () => {
    expect(cellText({ kind: "value", value: 3.0249 }, fmtD)).toBe("3.02");
    expect(cellText({ kind: "unverifiable", reason: "travel cap" }, fmtD)).toBe(UNVERIFIABLE);
    expect(cellText({ kind: "none" }, fmtD)).toBe(DASH);
    expect(cellText(secondsCell(pellets, "5", "V"), fmtV)).toBe("unverifiable");
  });
  it("the reason in words takes the cap from the data", () => {
    expect(reasonText(pellets)).toBe(`the dream passed the recording's trusted range (${pellets.trusted_travel_su} su)`);
    expect(reasonText(lost)).toBe("the camera path was lost");
    expect(reasonText(calm)).toBe("");
  });
});

describe("the finding line", () => {
  it("is DESIGN's example for the default clip (the film's clip, departure at f88)", () => {
    expect(clipTitle(dive)).toBe("Freshwater, enhanced · Gen-4.5 · prompt N · 5 s");
    expect(finding(dive)).toBe("D passes 3 at frame 88 (3.7 s), 711 su in; every pixel still verified (V 1.00)");
  });

  it("no departure: D stays under 3, with the peak and where it is", () => {
    const peak = Math.max(...numbers(calm));
    expect(finding(calm)).toBe(`D stays under 3; peak ${peak.toFixed(2)} at frame ${calm.D.indexOf(peak)}`);
  });

  it("ran out first: says where and why, and that D stayed under 3 up to there", () => {
    const u = pellets.unverifiable_from!;
    const peak = Math.max(...numbers(pellets));
    expect(finding(pellets)).toBe(
      `Verification ran out at frame ${u} (${(u / pellets.fps).toFixed(1)} s): the dream passed the recording's trusted range (100 su). ` +
      `D stayed under 3 up to there; peak ${peak.toFixed(2)} at frame ${pellets.D.indexOf(peak)}`);
    expect(finding(lost)).toMatch(/^Verification ran out at frame \d+ \(\d\.\d s\): the camera path was lost\. D stayed under 3 up to there; peak \d\.\d\d at frame \d+$/);
  });

  it("a brief spike is not a departure and is not called 'under 3'", () => {
    const D = calm.D.map((d, i) => (i >= 40 && i < 43 ? 3.14 : d));
    const c = { ...calm, D, first_D3: null };
    expect(finding(c)).toBe("D tops 3 on 3 frames but never holds it for 12; peak 3.14 at frame 40");
    expect(finding({ ...c, D: c.D.map((d, i) => (i === 40 ? 3.14 : i > 40 && i < 43 ? 1 : d)) })).toMatch(/^D tops 3 on 1 frame but never/);
  });

  it("a departure and a loss: both are said", () => {
    const c = { ...dive, unverifiable_from: 100, unverifiable_reason: "path lost" as const };
    expect(finding(c)).toBe("D passes 3 at frame 88 (3.7 s), 711 su in; every pixel still verified (V 1.00); verification ran out at frame 100 (4.2 s): the camera path was lost");
  });

  it("a low V at the departure is said in words, not hidden behind 'verified': unseen, or a tracked moving object when one is there", () => {
    const verified = dive.verified.map((v, i) => (i === 88 ? 0.54 : v));
    expect(finding({ ...dive, verified })).toBe("D passes 3 at frame 88 (3.7 s), 711 su in; V 0.54: part of the frame is unseen");
    const moving = dive.moving_track.map((m, i) => (i === 88 ? true : m));
    expect(finding({ ...dive, verified, moving_track: moving })).toBe("D passes 3 at frame 88 (3.7 s), 711 su in; V 0.54: part of the frame is unseen, or covered by a tracked moving object");
  });
  it("'every pixel' only when V is exactly 1: 0.9972 shows as 1.00 and says V, not every pixel", () => {
    const v = (x: number) => ({ ...dive, verified: dive.verified.map((q, i) => (i === 88 ? x : q)) });
    expect(finding(v(1))).toContain("every pixel still verified (V 1.00)");
    expect(finding(v(0.9972))).toBe("D passes 3 at frame 88 (3.7 s), 711 su in; V 1.00");
  });

  it("a clip with nothing measured says so, and never prints NaN, undefined or null", () => {
    const none = { ...calm, D: calm.D.map(() => null) };
    expect(finding(none)).toBe("No frame could be measured.");
    for (const c of [dive, pellets, lost, calm, none]) expect(finding(c)).not.toMatch(/NaN|undefined|null|0\.00 /);
  });

  it("opens the cursor on the finding: the departure, else the peak", () => {
    expect(findingFrame(dive)).toBe(88);
    expect(findingFrame(calm)).toBe(calm.D.indexOf(Math.max(...numbers(calm))));
    expect(dAt(pellets, findingFrame(pellets)).kind).toBe("value");
    expect(dAt(lost, findingFrame(lost)).kind).toBe("value");
  });
});
