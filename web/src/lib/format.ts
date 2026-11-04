import type { Clip } from "../data/types";
import { D_THRESHOLD, type Reading } from "./series";

export const UNVERIFIABLE = "unverifiable";
export const DASH = "–";                         // a cell with no value; styled grey by the caller

/** D to two places. Gold means D > 3, so the text may never contradict it: 3.004 is shown 3.01 (above), 2.996 as 2.99 (not above). */
export function fmtD(d: number): string {
  const s = d.toFixed(2);
  if (s === "3.00" && d > D_THRESHOLD) return "3.01";
  if (s === "3.00" && d < D_THRESHOLD) return "2.99";
  return s;
}
export const fmtV = (v: number): string => v.toFixed(2);
/** A distance in su, rounded, with a true minus sign (−231, never -231). */
export const fmtSu = (v: number): string => { const r = Math.round(v); return r < 0 ? `\u2212${-r}` : String(Math.abs(r)); };
export const fmtSeconds = (f: number, fps: number, dp = 1): string => (f / fps).toFixed(dp);
export const fmtPercent = (share: number): string => `${Math.round(share * 100)} %`;

/** Why a clip stopped being verifiable, in words, with the cap taken from the data. */
export function reasonText(clip: Clip): string {
  switch (clip.unverifiable_reason) {
    case "travel cap": return `the dream passed the recording's trusted range (${fmtSu(clip.trusted_travel_su ?? 0)} su)`;
    case "path lost": return "the camera path was lost";
    default: return "";
  }
}

/** A reading as the cell shows it: the number, the word 'unverifiable', or a dash. */
export function cellText(r: Reading, fmt: (v: number) => string): string {
  return r.kind === "value" ? fmt(r.value) : r.kind === "unverifiable" ? UNVERIFIABLE : DASH;
}
