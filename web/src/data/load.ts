import { hasMedia, mediaUrl } from "./media";
import type { Clip, ClipsDoc, PathFile, PlanFile, RecordingBlock } from "./types";

/** Anything wrong with the data: the page shows the message, it never renders a half-read file. */
export class DataError extends Error {
  constructor(message: string) { super(message); this.name = "DataError"; }
}

export const SUPPORTED_VERSION = "v1";

const HEAT_KEYS = ["clip", "alpha", "dim", "unverified", "unverified_hatch", "unverified_reasons", "outlined", "outline", "unseen_rgb",
  "positive", "negative", "positive_means", "negative_means", "floor_ramp", "floor_means"] as const;
const RECORDING_KEYS = ["floor", "far_end", "trusted_travel_su", "start", "plan", "null_dream_D", "tank_relief", "floor_map"] as const;
const CLIP_KEYS = ["clip", "condition", "engine", "prompt", "seconds", "take", "n_frames", "fps", "floor", "path", "yaw_deg", "lost_from",
  "verified", "D", "D_at", "V_at", "first_D3", "far_end", "far_end_valid", "wall_frame", "travel", "path_disagreement",
  "path_disagreement_frame", "trusted_travel_su", "first_capped_frame", "assets", "relief", "unverifiable_from", "unverifiable_reason",
  "trusted_frames", "untrusted", "provenance", "prompt_text", "seed", "moving_track", "recording_key"] as const;
const PER_FRAME = ["path", "yaw_deg", "verified", "D", "moving_track"] as const;

const isObj = (x: unknown): x is Record<string, any> => typeof x === "object" && x !== null && !Array.isArray(x);

function need(o: Record<string, any>, keys: readonly string[], where: string) {
  for (const k of keys) if (!(k in o)) throw new DataError(`${where}: the key "${k}" is missing`);
}

export function parseClips(raw: unknown): ClipsDoc {
  if (!isObj(raw)) throw new DataError("clips.json: not an object");
  need(raw, ["version", "unit", "heat", "relief", "recordings", "clips"], "clips.json");
  if (raw.version !== SUPPORTED_VERSION) throw new DataError(`clips.json: version "${raw.version}", this page reads "${SUPPORTED_VERSION}"`);
  if (typeof raw.unit !== "string" || !/\(su\)$/.test(raw.unit)) throw new DataError(`clips.json: unit "${raw.unit}" is not su (uncorrected stereo units)`);
  need(raw.heat, HEAT_KEYS, "clips.json heat");
  for (const k of ["positive", "negative", "floor_ramp"])
    if (!Array.isArray(raw.heat[k]) || raw.heat[k].length < 2) throw new DataError(`clips.json heat: the ramp "${k}" needs at least two stops`);
  if (!isObj(raw.recordings)) throw new DataError("clips.json: recordings is not an object");
  for (const [k, r] of Object.entries(raw.recordings)) {
    if (!isObj(r)) throw new DataError(`recording ${k}: not an object`);
    need(r, RECORDING_KEYS, `recording ${k}`);
  }
  if (!Array.isArray(raw.clips) || raw.clips.length === 0) throw new DataError("clips.json: no clips");
  for (const c of raw.clips) {
    if (!isObj(c)) throw new DataError("clips.json: a clip is not an object");
    const id = String(c.clip);
    need(c, CLIP_KEYS, `clip ${id}`);
    for (const k of PER_FRAME)
      if (!Array.isArray(c[k]) || c[k].length !== c.n_frames)
        throw new DataError(`clip ${id}: ${k} has ${Array.isArray(c[k]) ? c[k].length : "no"} entries, expected ${c.n_frames} (n_frames)`);
    if (!(c.recording_key in raw.recordings)) throw new DataError(`clip ${id}: its recording "${c.recording_key}" is not in clips.json`);
    need(c.assets, ["gen", "heat", "real", "poster", "relief", "tank_relief", "path"], `clip ${id} assets`);
  }
  return raw as unknown as ClipsDoc;
}

export function parsePath(raw: unknown, clip: Clip): PathFile {
  if (!isObj(raw)) throw new DataError(`${clip.assets.path}: not an object`);
  need(raw, ["clip", "fps", "x", "z", "yaw_deg", "lost_from", "capped_from", "wall_frame", "far_end", "far_end_valid", "unverifiable_from", "trusted_frames", "unit"], clip.assets.path);
  if (raw.clip !== clip.clip) throw new DataError(`${clip.assets.path}: it is the path of "${raw.clip}", not "${clip.clip}"`);
  if (raw.unit !== "su") throw new DataError(`${clip.assets.path}: unit "${raw.unit}", expected su`);
  for (const k of ["x", "z", "yaw_deg"])
    if (!Array.isArray(raw[k]) || raw[k].length !== clip.n_frames) throw new DataError(`${clip.assets.path}: ${k} must have ${clip.n_frames} entries`);
  return raw as unknown as PathFile;
}

export function parsePlan(raw: unknown, condition: string): PlanFile {
  if (!isObj(raw)) throw new DataError(`plan of ${condition}: not an object`);
  need(raw, ["condition", "far_end", "profile", "unit", "trusted_travel_su"], `plan of ${condition}`);
  if (raw.unit !== "su") throw new DataError(`plan of ${condition}: unit "${raw.unit}", expected su`);
  if (!Array.isArray(raw.profile) || raw.profile.length < 2 || !raw.profile.every((p: unknown) => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite)))
    throw new DataError(`plan of ${condition}: profile must be a list of [X, Z] pairs`);
  return raw as unknown as PlanFile;
}

const cache = new Map<string, Promise<unknown>>();
export const clearCache = () => cache.clear();

async function getJson(path: string, base: string): Promise<unknown> {
  if (!hasMedia(base)) throw new DataError("No media host: this build has no VITE_MEDIA_BASE (the media host's divetwin/v1/ prefix). Set it and rebuild.");
  const url = mediaUrl(path, base);
  let p = cache.get(url);
  if (!p) {
    p = fetch(url).then(async (r) => {
      if (!r.ok) throw new DataError(`${url}: ${r.status}`);
      try { return await r.json(); } catch { throw new DataError(`${url}: the answer is not JSON (a server that answers any path with its home page does this)`); }
    });
    cache.set(url, p);
    p.catch(() => cache.delete(url));          // a failure is retried next time, never remembered
  }
  return p;
}

export const loadClips = async (base: string): Promise<ClipsDoc> => parseClips(await getJson("clips.json", base));
export const loadPath = async (clip: Clip, base: string): Promise<PathFile> => parsePath(await getJson(clip.assets.path, base), clip);
export const loadPlan = async (rec: RecordingBlock, condition: string, base: string): Promise<PlanFile> => parsePlan(await getJson(rec.plan, base), condition);
