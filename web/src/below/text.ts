// The page's own words below the fold. No digit appears in any of them except the two thresholds the page defines, which it
// interpolates from the constants (D_REF, D_THRESHOLD): every other figure on the page is read from clips.json
// (src/test/page.test.tsx enforces it).
import { D_REF, D_THRESHOLD } from "../lib/series";
import { farEndLabel } from "../lib/names";

/** Master plan section 7's statement, close to verbatim, then what D, V and the departure mean. */
export const STATEMENT: string[] = [
  "Depth on the generated side comes from a single-image model. It has no scale of its own, so it is fitted to the real tank by one scale and one shift, on the parts of the tank that never move.",
  "The real depth is an off-the-shelf stereo matcher on the dataset's own pairs, uncorrected for the tank's flat window, so every distance here is in the same uncorrected unit, never millimetres: uncorrected stereo units (su).",
  "The real tank beside the dream is rebuilt from that depth and re-seen from where the dream's camera went; grey is where no real camera ever looked.",
];
export const HOW_TO_READ: { term: string; text: string }[] = [
  { term: "D", text: `how far the dream's depth is from the real tank's, as a multiple of the floor: mono depth's own error on the real tank's frames. ${D_REF} is no worse than mono depth on the real tank; above ${D_THRESHOLD} the tank has changed shape (gold).` },
  { term: "V", text: "the share of the frame that the rebuilt tank covers, leaving out any tracked moving object. Where it is below one, part of the frame is unseen by any real camera, or something that moves is in the way." },
  { term: "Departure", text: `the first frame from which D stays above ${D_THRESHOLD} for half a second.` },
  { term: "Unverifiable", text: "no number: the path was lost, or the dream went past the range a recording's rebuilt tank can be trusted for. It is never shown as zero." },
];

/** The wall test's limit (call 82). Air has no far wall: its tank's end is transparent, so it is the far end as measured (call 28). */
export const wallTestLimit = (condition: string): string =>
  `A path anchored to the tank cannot follow a dream out through the ${farEndLabel(condition)}; the first sustained D above ${D_THRESHOLD} marks the departure.`;
export const WALL_TEST_LIMIT = wallTestLimit("");

/** What the relief's colour is, and is not (Delta 4). The caption, the still's label and the canvas's label all lead with it. */
export const RELIEF_COLOUR = "Colour: the gap as placed, not the heat.";
export const RELIEF_OUTLINE = "A tracked moving object is not outlined here.";
export const RELIEF_NOTE =
  `${RELIEF_COLOUR} The real tank is a wire surface and the dream a surface coloured by its gap to it, in the heat's colours. ${RELIEF_OUTLINE} The dream is placed by the recovered position and yaw; pitch and roll are not recorded, so this is the surface's own reading, not the heat itself.`;
export const RELIEF_STILL_NOTE = "A still: the gap at this frame, one cell per colour.";
export const RELIEF_NO_WEBGL = "This browser could not start WebGL, so the surfaces are shown as a still.";
