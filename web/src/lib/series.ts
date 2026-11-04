import type { Clip } from "../data/types";

/** pipeline/metrics.py: D > 3 for 12 frames in a row is the departure. D = 1 is the floor (mono depth's own error on the real tank). */
export const D_THRESHOLD = 3;
export const D_REF = 1;
export const D_RUN = 12;

/** What the page may say about one number at one frame. 'unverifiable' is never rendered as a number, 0.00 included. */
export type Reading =
  | { kind: "value"; value: number }
  | { kind: "unverifiable"; reason: string }
  | { kind: "none" };

export const isUnverifiable = (clip: Clip, f: number): boolean => clip.unverifiable_from !== null && f >= clip.unverifiable_from;

const read = (clip: Clip, f: number, v: number | null | undefined): Reading => {
  if (isUnverifiable(clip, f)) return { kind: "unverifiable", reason: clip.unverifiable_reason ?? "unverified" };
  return v === null || v === undefined || Number.isNaN(v) ? { kind: "none" } : { kind: "value", value: v };
};

export const dAt = (clip: Clip, f: number): Reading => read(clip, f, clip.D[f]);
/** V past a travel cap is stored as 0.0; the cap check comes first so that 0.0 is never read as a measurement. */
export const vAt = (clip: Clip, f: number): Reading => read(clip, f, clip.verified[f]);
/** Forward travel along the first camera's viewing axis (path z), the quantity far_end is measured in. */
export const forwardAt = (clip: Clip, f: number): Reading => read(clip, f, clip.path[f]?.[2]);

export function firstSustained(D: (number | null)[], thr = D_THRESHOLD, run = D_RUN): number | null {
  let count = 0;
  for (let k = 0; k < D.length; k++) {
    const d = D[k];
    count = d !== null && Number.isFinite(d) && d > thr ? count + 1 : 0;
    if (count === run) return k - run + 1;
  }
  return null;
}

export function peakD(clip: Clip): { value: number; frame: number } | null {
  let best: { value: number; frame: number } | null = null;
  clip.D.forEach((d, frame) => {
    if (d !== null && Number.isFinite(d) && !isUnverifiable(clip, frame) && (best === null || d > best.value)) best = { value: d, frame };
  });
  return best;
}

export const framesAbove = (clip: Clip, thr = D_THRESHOLD): number =>
  clip.D.reduce<number>((n, d, f) => (d !== null && !isUnverifiable(clip, f) && d > thr ? n + 1 : n), 0);

/** The clip table's cells: D or V at 0, 1, 2.5, 5 or 10 s. Seconds beyond the clip are 'none'. */
export function secondsCell(clip: Clip, key: string, series: "D" | "V"): Reading {
  const f = Math.round(Number(key) * clip.fps);
  if (f > clip.n_frames - 1) return { kind: "none" };
  return read(clip, f, (series === "D" ? clip.D_at : clip.V_at)[key]);
}
