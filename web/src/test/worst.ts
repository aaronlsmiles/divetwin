// Task 4.6, break-ui: the worst realistic data, applied at the page's one data boundary (the clips.json and path.json it fetches), never in
// the components. Shared by the Vitest page tests (src/test/worst.test.tsx) and the Playwright trail (e2e/worst.spec.ts), which both feed it
// to a fetch stub / route handler. Test-only: nothing in src/ imports this, so it never ships.
//
// Every case is something the pipeline or a person can produce:
//   offScale     a floor near zero makes D = abs_rel / floor huge: a dream that flares to D 40 (the table and the curve both see it)
//   longName     a recording named by a person, 60 characters, with spaces, as a dataset's short condition name might be
//   dead         a clip whose verification is gone from frame 0: the path lost at once (V and D null) or the travel cap hit at once
//                (the pipeline writes V = 0.0 after a cap, which must never read as a measurement)
//   missing      a 404 on the relief atlas and on the recording's floor preview (the routes, not the data)
//   The 10 s dive at its last frame needs no mutation: ?clip=air__gen45__D__10s&f=240.

export const LONG_NAME_60 = "Saltwater pellets, second deployment, the long northern tank";   // exactly 60 characters (a test holds it)

type J = any;
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));

export function offScale(doc: J, id: string, value = 40): J {
  const d = clone(doc);
  const c = d.clips.find((x: J) => x.clip === id);
  const from = c.first_D3 ?? Math.floor(c.n_frames * 0.7);
  for (let k = from; k < c.n_frames; k++) if (c.D[k] !== null) c.D[k] = value;
  if (c.D_float) for (let k = from; k < c.n_frames; k++) if (c.D_float[k] !== null) c.D_float[k] = value;
  for (const [s, v] of Object.entries(c.D_at)) if (v !== null && Number(s) * c.fps >= from) c.D_at[s] = value;
  return d;
}

/** Rename a recording's condition for every clip that has it (the names come from the condition key unless a short name is known). */
export function longName(doc: J, condition: string, name = LONG_NAME_60): J {
  const d = clone(doc);
  for (const c of d.clips) if (c.condition === condition) c.condition = name;
  return d;
}

export type DeadReason = "path lost" | "travel cap";

/** The clip with nothing verifiable from frame 0. Returns the clips.json and the path.json to serve for it. */
export function dead(doc: J, path: J, id: string, reason: DeadReason): { doc: J; path: J } {
  const d = clone(doc), p = clone(path);
  const c = d.clips.find((x: J) => x.clip === id);
  const n = c.n_frames;
  c.unverifiable_from = 0; c.unverifiable_reason = reason; c.trusted_frames = 0;
  c.path = Array.from({ length: n }, () => [null, null, null]);
  c.yaw_deg = Array.from({ length: n }, () => null);
  c.D = Array.from({ length: n }, () => null);
  if (c.D_float) c.D_float = Array.from({ length: n }, () => null);
  c.moving_track = Array.from({ length: n }, () => false);
  c.first_D3 = null; c.path_disagreement = null; c.path_disagreement_frame = null; c.wall_frame = null; c.travel = 0;
  for (const k of Object.keys(c.D_at)) c.D_at[k] = null;
  if (reason === "travel cap") {
    c.verified = Array.from({ length: n }, () => 0.0);              // what the pipeline writes after a cap
    for (const k of Object.keys(c.V_at)) c.V_at[k] = 0.0;
    c.lost_from = null; c.first_capped_frame = 0; c.trusted_travel_su = 0;
  } else {
    c.verified = Array.from({ length: n }, () => null);
    for (const k of Object.keys(c.V_at)) c.V_at[k] = null;
    c.lost_from = 0; c.first_capped_frame = null;
  }
  p.x = Array.from({ length: n }, () => null); p.z = Array.from({ length: n }, () => null); p.yaw_deg = Array.from({ length: n }, () => null);
  p.unverifiable_from = 0; p.trusted_frames = 0;
  p.lost_from = reason === "path lost" ? 0 : null; p.capped_from = reason === "travel cap" ? 0 : null;
  return { doc: d, path: p };
}

/** The paths a fault test answers 404 to: the relief atlases (both) and the recording's floor preview. */
export const MISSING = [/\/relief\.png$/, /\/tank_relief\.png$/, /\/floor_preview\.jpg$/];
