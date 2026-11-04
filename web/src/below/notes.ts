import type { Clip } from "../data/types";
import { farEndLabel } from "../lib/names";

export interface Note { id: string; text: string }

/** Per-clip notes from the findings (calls 76, 77, 79, 85). Words only: any figure comes from the clip, never from here. */
export function notesFor(c: Clip): Note[] {
  const out: Note[] = [];
  if (c.clip === "air__wan22__N__5s") {
    out.push({ id: "air-wan-n-mask", text: "The tracked outline starts on a dark flash that later resolves into the military tank (the vehicle) the dream invents. It is left exactly as the tracker made it." });
  }
  if (c.unverifiable_reason === "travel cap") {
    out.push({ id: "cap", text: `This recording's rebuilt tank is only trusted up to ${Math.round(c.trusted_travel_su ?? 0)} su of travel. From frame ${c.unverifiable_from} on, everything is hatched and nothing is measured, even if the dream's own path drifts back. That is the conservative reading.` });
  }
  if (c.unverifiable_reason === "path lost") {
    out.push({ id: "lost", text: `The camera path was lost at frame ${c.unverifiable_from}. It is never extrapolated, so nothing from there on is measured.` });
  }
  if (c.moving_track.some((m) => m === true)) {
    out.push({ id: "tracked", text: "Something moves in this clip. It is outlined and its gap is drawn, but it is not counted in D, so that a swimmer or a vehicle cannot bend the path. A large tracked object can still raise D on the pixels around it." });
  }
  if (c.condition === "saltwater") {
    out.push({ id: "saltwater", text: "On saltwater the path rests on the dream's own texture once it has travelled far, because the tank's renders stop holding it. Read long saltwater paths with that in mind." });
  }
  out.push({ id: "v-limit", text: `V cannot see a dream leave the tank, only D can: a dream that goes through the ${farEndLabel(c.condition)} can keep a high V.` });
  return out;
}
