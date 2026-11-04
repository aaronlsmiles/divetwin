import { describe, expect, it } from "vitest";
import { gradientCss, hatchGrey, hatchIndex, hatchPattern, rampAt, residualColour, rgbCss } from "./palette";
import { parseClips } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";

const heat = parseClips(readFixtureJson("clips.json")).heat;

describe("heat palette, read from clips.json", () => {
  it("rampAt matches pipeline/heat.py's ramp() at the stops and between them", () => {
    expect(rampAt(heat.positive, 0).map(Math.round)).toEqual([74, 28, 12]);
    expect(rampAt(heat.positive, 0.25).map((v) => +v.toFixed(1))).toEqual([144, 70, 22]);      // python: heat.ramp(POSITIVE, 0.25)
    expect(rampAt(heat.positive, 0.75).map((v) => +v.toFixed(1))).toEqual([234.5, 174, 101]);
    expect(rampAt(heat.negative, 0.1).map((v) => +v.toFixed(1))).toEqual([16.8, 48.8, 100.4]);
    expect(rampAt(heat.negative, 0.9).map((v) => +v.toFixed(1))).toEqual([156, 210.4, 245.2]);
    expect(rampAt(heat.negative, 7)).toEqual(heat.negative[2][1]);                                // clipped
  });

  it("a signed residual picks the ramp by sign and the place by |r| clipped at heat.clip", () => {
    expect(residualColour(heat, 0.25)).toEqual(rampAt(heat.positive, 0.5));
    expect(residualColour(heat, -0.25)).toEqual(rampAt(heat.negative, 0.5));
    expect(residualColour(heat, 5)).toEqual(heat.positive[2][1]);
    expect(residualColour(heat, -5)).toEqual(heat.negative[2][1]);
    expect(residualColour(heat, 0)).toEqual(rampAt(heat.negative, 0));       // r = 0 is a dark ramp end, as in heat.py, never the hatch
    expect(residualColour(heat, Number.NaN)).toBeNull();
  });

  it("builds the key's gradients and swatches from the same numbers", () => {
    expect(rgbCss([74, 28, 12])).toBe("rgb(74,28,12)");
    expect(gradientCss(heat.positive)).toBe("linear-gradient(90deg, rgb(74,28,12) 0%, rgb(214,112,32) 50%, rgb(255,236,170) 100%)");
  });

  it("the hatch is heat.hatch(): row 0 and row 3 of python's hatch(6, 30)", () => {
    const row = (y: number) => Array.from({ length: 30 }, (_, x) => hatchGrey(x, y, heat));
    expect(row(0)).toEqual([96, 96, 96, 96, 96, 96, 128, 128, 128, 128, 128, 128, 96, 96, 96, 96, 96, 128, 128, 128, 128, 128, 128, 96, 96, 96, 96, 96, 96, 128]);
    expect(row(3)).toEqual([96, 96, 96, 128, 128, 128, 128, 128, 128, 96, 96, 96, 96, 96, 128, 128, 128, 128, 128, 128, 96, 96, 96, 96, 96, 96, 128, 128, 128, 128]);
  });

  it("the hatch is constant along x + y, and a stripe is 4 px across (5.66 px along an axis)", () => {
    const s = heat.unverified_hatch.stripe_px;
    for (let i = 0; i < 40; i++) expect(hatchIndex(i, 20 - (i % 20), s)).toBe(hatchIndex(i + 5, 15 - (i % 20), s));
    const edges: number[] = [];
    for (let x = 1; x < 400; x++) if (hatchIndex(x, 0, s) !== hatchIndex(x - 1, 0, s)) edges.push(x);
    const along = (edges[edges.length - 1] - edges[0]) / (edges.length - 1);
    expect(along / Math.SQRT2).toBeCloseTo(s, 1);
  });

  it("the SVG pattern's numbers come from the palette, not from the page", () => {
    expect(hatchPattern(heat)).toEqual({ size: 2 * heat.unverified_hatch.stripe_px, stripe: heat.unverified_hatch.stripe_px, greys: heat.unverified_hatch.greys, angle: 45 });
  });
});
