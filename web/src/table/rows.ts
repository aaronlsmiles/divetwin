import type { Clip } from "../data/types";
import { conditionName, engineName } from "../lib/names";
import { secondsCell, type Reading } from "../lib/series";

export type ColumnKey = "recording" | "engine" | "prompt" | "length" | "d5" | "v5" | "d10" | "v10" | "departure" | "travel";
export const COLUMNS: { key: ColumnKey; label: string; numeric: boolean }[] = [
  { key: "recording", label: "Recording", numeric: false }, { key: "engine", label: "Engine", numeric: false },
  { key: "prompt", label: "Prompt", numeric: false }, { key: "length", label: "Length", numeric: true },
  { key: "d5", label: "D at 5 s", numeric: true }, { key: "v5", label: "V at 5 s", numeric: true },
  { key: "d10", label: "D at 10 s", numeric: true }, { key: "v10", label: "V at 10 s", numeric: true },
  { key: "departure", label: "Departure", numeric: true }, { key: "travel", label: "Travel", numeric: true },
];

export interface Row { clip: Clip; order: number; d5: Reading; v5: Reading; d10: Reading; v10: Reading }

export const rowsOf = (clips: Clip[]): Row[] =>
  clips.map((clip, order) => ({ clip, order, d5: secondsCell(clip, "5", "D"), v5: secondsCell(clip, "5", "V"), d10: secondsCell(clip, "10", "D"), v10: secondsCell(clip, "10", "V") }));

/** The sort value of a column; null for a cell with no number (a dash, or the word unverifiable), which always sorts last. */
export function sortValue(r: Row, key: ColumnKey): number | string | null {
  const num = (x: Reading) => (x.kind === "value" ? x.value : null);
  switch (key) {
    case "recording": return conditionName(r.clip.condition);
    case "engine": return engineName(r.clip.engine);
    case "prompt": return r.clip.prompt;
    case "length": return r.clip.seconds;
    case "d5": return num(r.d5); case "v5": return num(r.v5); case "d10": return num(r.d10); case "v10": return num(r.v10);
    case "departure": return r.clip.first_D3;
    case "travel": return r.clip.travel;
  }
}

/** Stable sort by a column; cells without a number go last whichever way it runs. `null` key: the file's own order. */
export function sortRows(rows: Row[], key: ColumnKey | null, dir: "asc" | "desc"): Row[] {
  if (key === null) return [...rows].sort((a, b) => a.order - b.order);
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = sortValue(a, key), y = sortValue(b, key);
    if (x === null && y === null) return a.order - b.order;
    if (x === null) return 1;
    if (y === null) return -1;
    const c = typeof x === "string" ? x.localeCompare(y as string) : x - (y as number);
    return c !== 0 ? sign * c : a.order - b.order;
  });
}
