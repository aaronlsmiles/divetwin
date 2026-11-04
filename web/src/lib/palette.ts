import type { HeatPalette, Rgb, Stop } from "../data/types";

// Everything here reads the palette that pipeline/heat.py wrote into clips.json (heat.palette_json). No colour is typed in the page.
export const rgbCss = (c: Rgb | number[]): string => `rgb(${c[0]},${c[1]},${c[2]})`;

export function rampAt(stops: Stop[], t: number): Rgb {
  const x = Math.min(1, Math.max(0, t));
  for (let i = 1; i < stops.length; i++) {
    const [t0, c0] = stops[i - 1], [t1, c1] = stops[i];
    if (x <= t1) {
      const u = t1 === t0 ? 0 : (x - t0) / (t1 - t0);
      return [0, 1, 2].map((k) => c0[k] + (c1[k] - c0[k]) * u) as Rgb;
    }
  }
  return stops[stops.length - 1][1];
}

export const gradientCss = (stops: Stop[]): string =>
  `linear-gradient(90deg, ${stops.map(([t, c]) => `${rgbCss(c)} ${Math.round(t * 100)}%`).join(", ")})`;

/** The colour of a signed residual: the ramp by sign, the place on it by |r| clipped at heat.clip. NaN: null (unverified). */
export function residualColour(heat: HeatPalette, r: number): Rgb | null {
  if (!Number.isFinite(r)) return null;
  return rampAt(r > 0 ? heat.positive : heat.negative, Math.min(Math.abs(r), heat.clip) / heat.clip);
}

/** heat.hatch(): which of the two greys a pixel is, 0 or 1. Constant along x + y; a stripe is `stripePx` across the stripe. */
export const hatchIndex = (x: number, y: number, stripePx: number): number => Math.floor((x + y) / (stripePx * Math.SQRT2)) % 2;
export const hatchGrey = (x: number, y: number, heat: HeatPalette): number =>
  heat.unverified_hatch.greys[hatchIndex(x, y, heat.unverified_hatch.stripe_px)];

/** The hatch as an SVG <pattern>'s numbers. Rotated 45 degrees, vertical stripes of `stripePx` run along x + y: the same picture as hatch(). */
export function hatchPattern(heat: HeatPalette) {
  const { stripe_px: s, greys, angle_deg } = heat.unverified_hatch;
  return { size: 2 * s, stripe: s, greys, angle: angle_deg };
}
