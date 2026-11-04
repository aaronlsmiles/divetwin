// The shapes of runs/assets/clips.json (pipeline/assets.py, BLOCK_KEYS), clips/<id>/path.json and recordings/<c>/plan.json.
// Only keys the page reads are listed; the loader (load.ts) checks every one of them is present before anything renders.
export type Rgb = [number, number, number];
export type Stop = [number, Rgb];

/** heat.palette_json(): everything the legend and the marks are drawn from. Nothing here is retyped in the page. */
export interface HeatPalette {
  clip: number;
  alpha: number;
  dim: number;
  unverified: string;
  unverified_hatch: { angle_deg: number; stripe_px: number; greys: [number, number] };
  unverified_reasons: string[];
  outlined: string;
  outline: { rgb: Rgb; width_px: number };
  unseen_rgb: Rgb;
  positive: Stop[];
  negative: Stop[];
  positive_means: string;
  negative_means: string;
  floor_ramp: Stop[];                       // the floor map's own ramp (no sign, no meaning)
  floor_means: string;                      // what the floor map is, in words
}

export interface Png16Meta {
  cell: [number, number];
  depth_scale: number;
  unit: string;
  invalid: number;
  encoding: string;
}

export interface ReliefMeta extends Png16Meta {
  cols: number;
  rows: number;
  frames: number;
  box: [number, number, number, number];
  real_size: [number, number];
  /** The cell's pinhole intrinsics (pipeline task C0): the real camera's, scaled to the mapping box and the 160 x 90 cell. */
  fx?: number;
  fy?: number;
  cx?: number;
  cy?: number;
}

export interface RecordingBlock {
  floor: number;
  far_end: number;
  trusted_travel_su: number | null;
  start: string;
  plan: string;
  null_dream_D: { median: number; max: number };
  null_dream_D_float: number;
  tank_relief: Png16Meta & { png: string };
  floor_map: {
    png: string; preview: string; grid: [number, number]; clip: number; min_obs: number; stored: string; encoding: string;
    display_only: boolean; observed_share: number; pixel_median: number | null; pixel_median_note: string; floor_check: number;
  };
}

export interface ClipAssets {
  gen: string; heat: string; real: string; poster: string; poster_heat: string; relief: string; tank_relief: string; path: string;
}

export type Pt3 = [number | null, number | null, number | null];
export type UnverifiableReason = "travel cap" | "path lost";

export interface Clip {
  clip: string;
  condition: string;
  engine: string;
  prompt: string;
  seconds: number;
  take: number | null;
  n_frames: number;
  fps: number;
  floor: number;
  path: Pt3[];                              // [x, y, z] in su; [null, null, null] from unverifiable_from on
  yaw_deg: (number | null)[];
  lost_from: number | null;
  verified: (number | null)[];              // V; past a travel cap the pipeline writes 0.0 (never shown: see series.ts)
  D: (number | null)[];                     // null where unverifiable
  D_at: Record<string, number | null>;      // keys "0" "1" "2.5" "5" "10" (seconds)
  V_at: Record<string, number | null>;
  first_D3: number | null;                  // first frame of 12 in a row above 3
  far_end: number | null;
  far_end_valid: boolean;
  wall_frame: number | null;
  travel: number;                           // straight-line start to last trusted frame, su
  path_disagreement: number | null;         // su; null past the cap or when the second path was lost
  path_disagreement_frame: number | null;
  trusted_travel_su: number | null;
  first_capped_frame: number | null;
  assets: ClipAssets;
  relief: ReliefMeta;
  unverifiable_from: number | null;
  unverifiable_reason: UnverifiableReason | null;
  trusted_frames: number;
  untrusted: { travel?: number; wall_frame?: number | null };
  provenance: Record<string, string>;
  prompt_text: string;
  seed: number;
  moving_track: (boolean | null)[];
  recording_key: string;
}

export interface ClipsDoc {
  version: string;
  unit: string;
  heat: HeatPalette;
  relief: { cols: number; cell: [number, number]; depth_scale: number };
  recordings: Record<string, RecordingBlock>;
  clips: Clip[];
}

export interface PathFile {
  clip: string;
  fps: number;
  x: (number | null)[];
  z: (number | null)[];
  yaw_deg: (number | null)[];
  lost_from: number | null;
  capped_from: number | null;
  wall_frame: number | null;
  far_end: number | null;
  far_end_valid: boolean;
  unverifiable_from: number | null;
  trusted_frames: number;
  primary_path: string;
  unit: string;
}

export interface PlanFile {
  condition: string;
  far_end: number;
  profile: [number, number][];              // [X, Z] in su: the tank seen from above at mid-height
  unit: string;
  trusted_travel_su: number | null;
}
