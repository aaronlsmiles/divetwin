import { describe, expect, it } from "vitest";
import { agreementText, pathAgreement, SHARE_FLOOR_SU } from "./agreement";
import { parseClips } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";

const [dive, pellets, lost, calm] = parseClips(readFixtureJson("clips.json")).clips;

describe("path agreement (call 78)", () => {
  it("is the second path's gap in su, and that gap as a share of max(travel, 200 su)", () => {
    const a = pathAgreement(dive)!;
    expect(a.su).toBe(dive.path_disagreement);
    expect(a.of).toBe(Math.max(dive.travel, 200));
    expect(a.share).toBeCloseTo(dive.path_disagreement! / dive.travel, 12);
    expect(a.frame).toBe(dive.path_disagreement_frame);
    expect(SHARE_FLOOR_SU).toBe(200);
  });
  it("a short run is measured against 200 su, so a near-still clip never reads as thousands of percent", () => {
    const still = { ...calm, travel: 2, path_disagreement: 90 };
    const a = pathAgreement(still)!;
    expect(a.of).toBe(200);
    expect(a.share).toBeCloseTo(0.45, 12);
  });
  it("is null where the pipeline wrote null (past the cap, or the second path lost): nothing is said", () => {
    expect(pathAgreement(pellets)).toBeNull();
    expect(pathAgreement(lost)).toBeNull();
  });
  it("is worded in su and a share, never as an error bar", () => {
    const t = agreementText(pathAgreement(dive)!);
    expect(t.su).toBe(`${Math.round(dive.path_disagreement!)} su`);
    expect(t.share).toMatch(/^\d+ % of max\(travel, 200 su\)$/);
    expect(`${t.su} ${t.share}`).not.toMatch(/±|error/i);
  });
});
