import { scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import type { Clip } from "../data/types";
import { D_THRESHOLD, isUnverifiable } from "../lib/series";

export const Y_MAX_MIN = 4;                     // the D axis always shows the 3 line with room above it
export const Y_MAX_CAP = 8;                     // a D past this is drawn at the top edge; the number is in the readout

export type Series = (number | null)[];
export interface Seg { gold: boolean; pts: [number, number][] }       // pts are [frame, value], with the value cut at the threshold

/** D (or V) by frame with every unverifiable frame null, so a curve can never run on past where the evidence stops. */
export const trustedSeries = (clip: Clip, values: Series): Series => values.map((v, f) => (isUnverifiable(clip, f) ? null : v));

export function yMaxFor(values: Series): number {
  const m = Math.max(0, ...values.filter((v): v is number => v !== null && Number.isFinite(v)));
  return Math.min(Y_MAX_CAP, Math.max(Y_MAX_MIN, Math.ceil(m)));
}

/** Runs of the curve, ink at or below `thr` and gold above it, cut exactly where the line crosses it. A null breaks the run. */
export function splitAtThreshold(values: Series, thr = D_THRESHOLD): Seg[] {
  const segs: Seg[] = [];
  const push = (gold: boolean, a: [number, number], b: [number, number]) => {
    const last = segs[segs.length - 1];
    if (last && last.gold === gold && last.pts[last.pts.length - 1][0] === a[0] && last.pts[last.pts.length - 1][1] === a[1]) last.pts.push(b);
    else segs.push({ gold, pts: [a, b] });
  };
  for (let i = 0; i + 1 < values.length; i++) {
    const a = values[i], b = values[i + 1];
    if (a === null || b === null || !Number.isFinite(a) || !Number.isFinite(b)) continue;
    const pa: [number, number] = [i, a], pb: [number, number] = [i + 1, b];
    if ((a > thr) === (b > thr)) { push(a > thr, pa, pb); continue; }
    const x = i + (thr - a) / (b - a);
    const mid: [number, number] = [x, thr];
    push(a > thr, pa, mid);
    push(b > thr, mid, pb);
  }
  return segs;
}

export interface Track { x: (frame: number) => number; y: (value: number) => number; w: number; h: number; yMax: number }

/** A track's scales. x runs frame 0 to n - 1 across the width; y runs 0 at the bottom to yMax at the top, values above yMax cut to it. */
export function makeTrack(n: number, w: number, h: number, yMax: number, pad = 2): Track {
  const sx = scaleLinear().domain([0, n - 1]).range([0, w]);
  const sy = scaleLinear().domain([0, yMax]).range([h - pad, pad]).clamp(true);
  return { x: (f) => sx(f), y: (v) => sy(v), w, h, yMax };
}

/** The D track's floor: every clip's D at frame 0 is 0.76 to 1.04 and its null dream 0.68 to 1.33, so the axis starts at 0.5 and a D under it is
 *  drawn on the bottom edge (the readout says the number). */
export const D_AXIS_MIN = 0.5;
/** Above the departure line the scale runs at half the pixels per unit: the gold is a different regime, and the spend of the track goes to
 *  where the dreams that hold sit (1 to 3). Task 4.6: 1 to 3 was 15 px of 48 on the default clip, now 22; the line at 3 and the line at 1 stay labelled. */
export const D_UPPER_SLOPE = 0.5;

/** The D curve's scales: piecewise linear, D_AXIS_MIN to 3 at full slope, 3 to yMax at half of it. */
export function makeDTrack(n: number, w: number, h: number, yMax: number, pad = 2): Track {
  const sx = scaleLinear().domain([0, n - 1]).range([0, w]);
  const lower = D_THRESHOLD - D_AXIS_MIN, upper = D_UPPER_SLOPE * Math.max(0, yMax - D_THRESHOLD);
  const usable = h - 2 * pad;
  const y3 = h - pad - (usable * lower) / (lower + upper);
  const sy = scaleLinear().domain([D_AXIS_MIN, D_THRESHOLD, yMax]).range([h - pad, y3, pad]).clamp(true);
  return { x: (f) => sx(f), y: (v) => sy(v), w, h, yMax };
}

const lineOf = line<[number, number]>();
export const pathD = (t: Track, seg: Seg): string =>
  lineOf.x((p) => t.x(p[0])).y((p) => t.y(p[1]))(seg.pts) ?? "";
