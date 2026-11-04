import { memo, useMemo, useState } from "react";
import type { Clip } from "../data/types";
import { cellText, DASH, fmtD, fmtSu, fmtV } from "../lib/format";
import { clipTitle } from "../lib/finding";
import { conditionName, engineName } from "../lib/names";
import { COLUMNS, rowsOf, sortRows, type ColumnKey } from "./rows";
import type { Reading } from "../lib/series";
import { D_THRESHOLD } from "../lib/series";
import "./table.css";

/** The phone row's breadcrumb after the recording: " · Gen-4.5 · prompt N · 5 s", with no-break spaces where a line must not end or begin
 *  (before each "·", and inside "Gen-4.5", "Wan 2.2", "prompt N" and "5 s"), so a wrapped row ends a line on a "·" and never starts one with it (task 4.6). */
export const crumbOf = (c: Clip): string => {
  const whole = (t: string) => t.replace(/ /g, "\u00a0").replace(/-/g, "\u2060-\u2060");   // "Gen-4.5", "Wan 2.2", "prompt N" and "5 s" are each one unit (a word joiner holds a hyphen)
  return `\u00a0\u00b7 ${whole(engineName(c.engine))}\u00a0\u00b7 ${whole(`prompt ${c.prompt}`)}\u00a0\u00b7 ${whole(`${c.seconds} s`)}`;
};

/** All clips as one table (memoised: the frame changes 24 times a second while playing and the table does not depend on it). Rows load the stage; a cell with no value is a grey dash, a cell past a cap says unverifiable (never 0.00). */
/** `only`: the findings band's group (call 92), the clip ids to show; null shows every clip. */
export const ClipTable = memo(function ClipTable({ clips, current, onPick, only = null }: { clips: Clip[]; current: string; onPick: (id: string) => void; only?: ReadonlySet<string> | null }) {
  const [sort, setSort] = useState<{ key: ColumnKey | null; dir: "asc" | "desc" }>({ key: null, dir: "asc" });
  const rows = useMemo(() => sortRows(rowsOf(clips), sort.key, sort.dir).filter((r) => only === null || only.has(r.clip.clip)), [clips, sort, only]);
  const toggle = (key: ColumnKey) => setSort((s) => (s.key === key ? (s.dir === "asc" ? { key, dir: "desc" } : { key: null, dir: "asc" }) : { key, dir: "asc" }));
  const cell = (text: string) => (text === DASH ? <span className="dash">{text}</span> : text);
  /** A D above 3 is set heavier so the departures can be scanned down the column: weight only, the colour stays as it is. */
  const dClass = (r: Reading) => `r num${r.kind === "value" && r.value > D_THRESHOLD ? " over" : ""}`;
  return (
    <div className="table-frame">
      <table className="data clip-table">
        <caption className="visually-hidden">All {clips.length} clips: D and V at 5 s and 10 s, the departure frame and the travel. Choose a row to load it.</caption>
        <thead>
          <tr>
            {COLUMNS.map((c) => (
              <th key={c.key} scope="col" className={c.numeric ? "r" : undefined} aria-sort={sort.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
                <button type="button" className="th-btn" onClick={() => toggle(c.key)}>{c.label}{sort.key === c.key ? (sort.dir === "asc" ? " ↑" : " ↓") : ""}</button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const c = r.clip, on = c.clip === current;
            return (
              <tr key={c.clip} className={on ? "is-active" : undefined} aria-current={on ? "true" : undefined} onClick={() => onPick(c.clip)}>
                <td data-col="recording" data-crumb={crumbOf(c)}><button type="button" className="row-btn" aria-label={clipTitle(c)} onClick={(e) => { e.stopPropagation(); onPick(c.clip); }}>{conditionName(c.condition)}</button></td>
                <td data-col="engine">{engineName(c.engine)}</td>
                <td data-col="prompt">{c.prompt}</td>
                <td className="r num" data-col="length">{c.seconds} s</td>
                <td className={dClass(r.d5)} data-col="d5" data-label="D 5 s">{cell(cellText(r.d5, fmtD))}</td>
                <td className="r num" data-col="v5" data-label="V 5 s">{cell(cellText(r.v5, fmtV))}</td>
                <td className={dClass(r.d10)} data-col="d10" data-label="D 10 s">{cell(cellText(r.d10, fmtD))}</td>
                <td className="r num" data-col="v10" data-label="V 10 s">{cell(cellText(r.v10, fmtV))}</td>
                <td className="r num" data-col="departure" data-label="Departure">{c.first_D3 === null ? <span className="dash">{DASH}</span> : `f${c.first_D3}`}</td>
                <td className="r num" data-col="travel" data-label="Travel">{fmtSu(c.travel)}<span className="unit"> su</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
});
