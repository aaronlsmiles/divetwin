import type { Clip } from "../data/types";
import { fmtPercent, fmtSu } from "./format";

/** Call 78 (Aaron, 4 Nov): the second path's disagreement is read in su, or as a share of max(travel, 200 su), never as an error bar. */
export const SHARE_FLOOR_SU = 200;

export interface Agreement { su: number; frame: number; of: number; share: number }

/** null where the second path was lost or the clip is past its cap (the pipeline nulls it there): nothing to say. */
export function pathAgreement(c: Clip): Agreement | null {
  if (c.path_disagreement === null || c.path_disagreement_frame === null) return null;
  const of = Math.max(c.travel, SHARE_FLOOR_SU);
  return { su: c.path_disagreement, frame: c.path_disagreement_frame, of, share: c.path_disagreement / of };
}

export function agreementText(a: Agreement): { su: string; share: string } {
  return { su: `${fmtSu(a.su)} su`, share: `${fmtPercent(a.share)} of max(travel, ${SHARE_FLOOR_SU} su)` };
}
