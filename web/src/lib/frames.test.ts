import { describe, expect, it } from "vitest";
import { clampFrame, frameFromTime, readout, stepFrame, timeFor } from "./frames";

describe("frames and time", () => {
  it("seeks to the middle of a frame, so the decoder lands on it and not the one before", () => {
    expect(timeFor(0, 24)).toBeCloseTo(1 / 48, 12);
    expect(timeFor(88, 24)).toBeCloseTo(88.5 / 24, 12);
    for (const f of [0, 1, 87, 88, 120, 240]) expect(frameFromTime(timeFor(f, 24), 24)).toBe(f);
  });
  it("clamps to the clip", () => {
    expect(clampFrame(-3, 121)).toBe(0);
    expect(clampFrame(500, 121)).toBe(120);
    expect(clampFrame(40.6, 121)).toBe(41);
    expect(clampFrame(Number.NaN, 121)).toBe(0);
  });
  it("reads the frame and the time as the scrubber shows them", () => {
    expect(readout(88, 24)).toBe("f88 · 3.67 s");
    expect(readout(0, 24)).toBe("f0 · 0.00 s");
    expect(readout(240, 24)).toBe("f240 · 10.00 s");
  });
});

describe("keyboard steps (arrows ±1, Shift ±12, Home and End)", () => {
  it("steps one frame, or twelve with Shift, and stops at the ends", () => {
    expect(stepFrame("ArrowRight", false, 10, 121)).toBe(11);
    expect(stepFrame("ArrowUp", false, 10, 121)).toBe(11);
    expect(stepFrame("ArrowLeft", false, 10, 121)).toBe(9);
    expect(stepFrame("ArrowDown", false, 10, 121)).toBe(9);
    expect(stepFrame("ArrowRight", true, 10, 121)).toBe(22);
    expect(stepFrame("ArrowLeft", true, 10, 121)).toBe(0);
    expect(stepFrame("ArrowRight", true, 115, 121)).toBe(120);
    expect(stepFrame("ArrowLeft", false, 0, 121)).toBe(0);
  });
  it("Home and End go to the ends; other keys are not ours", () => {
    expect(stepFrame("Home", false, 50, 121)).toBe(0);
    expect(stepFrame("End", false, 50, 121)).toBe(120);
    expect(stepFrame("End", false, 50, 241)).toBe(240);
    expect(stepFrame("a", false, 50, 121)).toBeNull();
    expect(stepFrame("Tab", false, 50, 121)).toBeNull();
  });
});
