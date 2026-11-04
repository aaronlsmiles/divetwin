// The figures the page may show for a clip at a frame, each derived from the raw clips.json by its own arithmetic (not by the
// page's formatters), so a figure that is hand-typed or computed wrongly is not in the set. Shared by the page test.
import type { Clip, ClipsDoc } from "../data/types";
import { D_REF, D_RUN, D_THRESHOLD } from "../lib/series";
import { SHARE_FLOOR_SU } from "../lib/agreement";
import { ENGINE_NAMES } from "../lib/names";
import { scaleTicks } from "../plan/geometry";

/** The only numerals the page may print that are not in the data. Each is a threshold or rule the page states, imported from the
 *  module that owns it; this list must stay this short. */
export const STRUCTURAL: Record<string, string> = {
  [String(D_REF)]: "D = 1, the floor (lib/series D_REF)",
  [String(D_THRESHOLD)]: "D = 3, the departure threshold (lib/series D_THRESHOLD)",
  [String(D_RUN)]: "12 frames in a row, the departure run (lib/series D_RUN)",
  [String(SHARE_FLOOR_SU)]: "max(travel, 200 su), call 78 (lib/agreement SHARE_FLOOR_SU)",
};

const dp = (v: number | null | undefined, n: number) => (v === null || v === undefined || !Number.isFinite(v) ? [] : [v.toFixed(n)]);
const int = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? [] : [String(Math.round(v))]);

export function allowedFor(doc: ClipsDoc, c: Clip, frame: number): Set<string> {
  const rec = doc.recordings[c.recording_key];
  const out: string[] = [...Object.keys(STRUCTURAL), ...dp(doc.heat.clip, 1), String(doc.clips.length), String(c.seconds), String(frame)];
  out.push(...dp(frame / c.fps, 2), ...dp(frame / c.fps, 1));
  // the cursor
  out.push(...dp(c.D[frame], 2), ...dp(c.verified[frame], 2), ...int(c.path[frame]?.[2]));
  // the finding line speaks of the departure frame whatever the cursor is on; the plan's axis counts su in its own steps
  if (c.first_D3 !== null) out.push(...int(c.path[c.first_D3]?.[2]), ...dp(c.verified[c.first_D3], 2));
  const zs = c.path.map((p) => p[2] ?? 0);
  out.push(...scaleTicks(Math.max(c.far_end ?? 0, ...zs), Math.min(0, ...zs)).map((t) => String(Math.abs(t))));
  // the clip
  out.push(...int(c.far_end), ...int(c.travel), ...int(c.trusted_travel_su), ...dp(rec.floor, 3), ...dp(3 * rec.floor, 3), ...dp(rec.null_dream_D.median, 2));
  for (const f of [c.first_D3, c.unverifiable_from, c.lost_from, c.path_disagreement_frame]) if (f !== null) out.push(String(f), ...dp(f / c.fps, 1), ...dp(f / c.fps, 2));
  if (c.path_disagreement !== null) out.push(...int(c.path_disagreement), String(Math.round((100 * c.path_disagreement) / Math.max(c.travel, 200))));
  const D = c.D.filter((d): d is number => d !== null);
  if (D.length) { const peak = Math.max(...D); out.push(...dp(peak, 2), String(c.D.indexOf(peak))); }
  const above = c.D.filter((d) => d !== null && d > D_THRESHOLD).length;
  if (above) out.push(String(above));
  // the table: every clip's own cells
  for (const o of doc.clips) {
    for (const k of Object.keys(o.D_at)) out.push(...dp(o.D_at[k], 2), ...dp(o.V_at[k], 2));
    if (o.first_D3 !== null) out.push(String(o.first_D3));
    out.push(...int(o.travel), String(o.seconds));
  }
  // the table's columns are named after the D_at / V_at keys (seconds) the data has
  for (const o of doc.clips) out.push(...Object.keys(o.D_at));
  return new Set(out);
}

/** The numerals in some text. */
export const numerals = (text: string): string[] => text.match(/\d+(?:\.\d+)?/g) ?? [];

/** Attributes a screen reader or a tooltip speaks: a figure there is a figure on the page. */
const SPOKEN = ["aria-label", "aria-valuetext", "alt", "title"] as const;

/** The page's visible words, text node by text node with a space between (so "88" and "773" never fuse), **and the words in aria-label,
 *  aria-valuetext, alt and title**, without the static prose (statement, credits: checked against STATIC_NUMERALS), the mono provenance
 *  block, and the engines' names (Gen-4.5, Wan 2.2: names, not figures). */
export function pageText(root: HTMLElement): string {
  const clone = root.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("[data-static], .mono, script, style").forEach((e) => e.remove());
  const parts: string[] = [];
  const walk = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode()) parts.push(n.textContent ?? "");
  clone.querySelectorAll(SPOKEN.map((a) => `[${a}]`).join(",")).forEach((e) => SPOKEN.forEach((a) => { const v = e.getAttribute(a); if (v) parts.push(v); }));
  let text = parts.join(" ");
  for (const name of Object.values(ENGINE_NAMES)) text = text.split(name).join(" ");
  return text;
}

/** The static regions' words (statement and credits). */
export function staticText(root: HTMLElement): string {
  return [...root.querySelectorAll("[data-static]")].map((e) => e.textContent ?? "").join(" ");
}

/**
 * The numerals the static prose may hold, each with where it comes from. Model names and versions, licences and the DOI are names,
 * not measurements; the two thresholds are the page's own rule. Anything else in the statement or the credits fails the page test.
 */
export const STATIC_NUMERALS: Record<string, string> = {
  [String(D_REF)]: "D = 1 (the statement's threshold, lib/series D_REF)",
  [String(D_THRESHOLD)]: "D = 3 (the statement's threshold) and Depth Anything 3 (credits)",
  "4.0": "CC BY 4.0, CC BY-NC 4.0 and CC BY-NC-SA 4.0 (licences)",
  "2.0": "Apache-2.0 (licence)",
  "2": "Depth Anything V2 and SAM 2.1's major version (model names)",
  "2.1": "SAM 2.1 (model name)",
  "2.2": "Wan 2.2 (model name)",
  "5": "Wan 2.2 TI2V-5B (model name)",
  "4.5": "Runway Gen-4.5 (model name)",
  "2025": "CVPR 2025 (Stereo Anywhere's venue, as credited in MODELS.md)",
  "10.5281": "the dataset's DOI prefix",
  "16753748": "the dataset's DOI suffix",
};
