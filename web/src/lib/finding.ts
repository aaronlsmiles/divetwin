import type { Clip } from "../data/types";
import { conditionName, engineName } from "./names";
import { fmtD, fmtSeconds, fmtSu, fmtV, reasonText } from "./format";
import { D_RUN, D_THRESHOLD, framesAbove, peakD } from "./series";

/** "Freshwater, enhanced · Gen-4.5 · prompt N · 5 s": the h1. */
export const clipTitle = (c: Clip): string => `${conditionName(c.condition)} · ${engineName(c.engine)} · prompt ${c.prompt} · ${c.seconds} s`;

/** V is the share of the frame the rebuilt tank covers, leaving out a tracked moving object. "Every pixel" is said only when V is
 *  exactly 1 (it shows as 1.00 from 0.995 up, which is not every pixel); below that V is given, with what the gap can be. */
const vClause = (v: number | null, moving: boolean): string =>
  v === null ? "" : v === 1 ? `every pixel still verified (V ${fmtV(v)})` : v >= 0.995 ? `V ${fmtV(v)}`
    : `V ${fmtV(v)}: part of the frame is unseen${moving ? ", or covered by a tracked moving object" : ""}`;

/**
 * The line under the title (docs/DESIGN.md), computed from the clip and never typed:
 *   departure   "D passes 3 at frame 88 (3.7 s), 711 su in; every pixel still verified (V 1.00)"
 *   a brief spike (above 3 but never for 12 frames in a row)
 *   no departure "D stays under 3; peak 1.9 at frame 120"
 *   ran out first  "Verification ran out at frame 20 (0.8 s): …. D stayed under 3 up to there; peak …"
 */
export function finding(c: Clip): string {
  const peak = peakD(c);
  const at = (f: number) => `frame ${f} (${fmtSeconds(f, c.fps)} s)`;
  const ran = c.unverifiable_from !== null ? `verification ran out at ${at(c.unverifiable_from)}: ${reasonText(c)}` : null;
  if (peak === null) return ran ? `${ran[0].toUpperCase()}${ran.slice(1)}; no frame could be measured.` : "No frame could be measured.";
  if (c.first_D3 !== null) {
    const f = c.first_D3;
    const fwd = c.path[f]?.[2];
    const where = fwd === null || fwd === undefined ? "" : `, ${fmtSu(fwd)} su in`;
    return `D passes ${D_THRESHOLD} at ${at(f)}${where}; ${vClause(c.verified[f], c.moving_track[f] === true)}${ran ? `; ${ran}` : ""}`;
  }
  const n = framesAbove(c);
  if (n > 0) {
    return `D tops ${D_THRESHOLD} on ${n} frame${n === 1 ? "" : "s"} but never holds it for ${D_RUN}; peak ${fmtD(peak.value)} at frame ${peak.frame}${ran ? `; ${ran}` : ""}`;
  }
  if (ran) return `${ran[0].toUpperCase()}${ran.slice(1)}. D stayed under ${D_THRESHOLD} up to there; peak ${fmtD(peak.value)} at frame ${peak.frame}`;
  return `D stays under ${D_THRESHOLD}; peak ${fmtD(peak.value)} at frame ${peak.frame}`;
}

/** Where the cursor opens: the departure, else the clip's peak D, else the start. The finding and the cursor agree. */
export function findingFrame(c: Clip): number {
  return c.first_D3 ?? peakD(c)?.frame ?? 0;
}
