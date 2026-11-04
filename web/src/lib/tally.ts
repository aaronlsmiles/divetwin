import type { Clip } from "../data/types";
import { findingKind, type FindingKind } from "./finding";
import { D_THRESHOLD, framesAbove, isUnverifiable } from "./series";

/** The band's order: the answer's own story, from leaving to never checked. */
export const TALLY_ORDER: FindingKind[] = ["departs", "spikes", "under", "unchecked"];

/** A group in words, after its count; the verb agrees with the count ("1 leaves", "3 leave"). */
export function tallyWords(kind: FindingKind, n: number): string {
  const one = n === 1;
  switch (kind) {
    case "departs": return `${one ? "leaves" : "leave"} the tank for good`;
    case "spikes": return `${one ? "spikes" : "spike"} past ${D_THRESHOLD}`;
    case "under": return `${one ? "stays" : "stay"} under ${D_THRESHOLD}`;
    case "unchecked": return "can't be checked to the end";
  }
}

export interface TallyGroup { kind: FindingKind; n: number; clips: Clip[] }

/** The clips counted by the finding line's own classification (lib/finding findingKind), in the file's order within a group.
 *  A kind no clip has is left out, so no count is a zero that leads nowhere. */
export function tally(clips: Clip[]): TallyGroup[] {
  return TALLY_ORDER
    .map((kind) => { const of = clips.filter((c) => findingKind(c) === kind); return { kind, n: of.length, clips: of }; })
    .filter((g) => g.n > 0);
}

/** V on the clip's measured frames (before any cap or loss), at its lowest. */
const lowestV = (c: Clip): number | null => {
  const v = c.verified.filter((x, f): x is number => x !== null && !isUnverifiable(c, f));
  return v.length ? Math.min(...v) : null;
};

/**
 * The band's second surprise, from the data: the engine whose clips past 3 all keep V at 1.00 (as the page shows it, 0.995 and up) on
 * every measured frame, with at least one of them a departure. Its V is the lowest of theirs. Nothing when no engine qualifies, or two do.
 */
export function steadyV(clips: Clip[]): { engine: string; v: number } | null {
  const past = clips.filter((c) => framesAbove(c) > 0);
  const found = [...new Set(past.map((c) => c.engine))].flatMap((engine) => {
    const own = past.filter((c) => c.engine === engine);
    const lows = own.map(lowestV);
    if (lows.some((v) => v === null || v < 0.995) || !own.some((c) => findingKind(c) === "departs")) return [];
    return [{ engine, v: Math.min(...(lows as number[])) }];
  });
  return found.length === 1 ? found[0] : null;
}
