import { useEffect, useState } from "react";
import type { Clip, ClipsDoc, PathFile, PlanFile } from "../data/types";
import { loadPath, loadPlan } from "../data/load";
import { fmtSu } from "../lib/format";
import { farEndLabel } from "../lib/names";
import { forwardAt } from "../lib/series";
import { wallTestLimit } from "../below/text";
import { cursorAt, farWall, makeView, pathRuns, scaleTicks, TICK_GUTTER, VIEW, wallPoints } from "./geometry";
import "./plan.css";

/** A tick label with a true minus sign (−200, never -200). */
const fmtSigned = (t: number): string => (t < 0 ? `\u2212${-t}` : String(t));

/** The path and the plan of the tank for a clip, fetched once each. */
export function usePlanData(doc: ClipsDoc, clip: Clip, base: string) {
  const [data, setData] = useState<{ clip: string; path: PathFile; plan: PlanFile } | "error" | null>(null);
  useEffect(() => {
    let live = true;
    setData(null);
    Promise.all([loadPath(clip, base), loadPlan(doc.recordings[clip.recording_key], clip.recording_key, base)])
      .then(([path, plan]) => live && setData({ clip: clip.clip, path, plan }), () => live && setData("error"));
    return () => { live = false; };
  }, [doc, clip, base]);
  return data;
}

/** The signature element: the tank from above, the far wall at its measured distance, the recovered path, the cursor. */
export function PlanView({ clip, plan, path, frame }: { clip: Clip; plan: PlanFile; path: PathFile; frame: number }) {
  const v = makeView(plan, path);
  const wall = farWall(plan);
  const runs = pathRuns(path, clip);
  const cur = cursorAt(path, frame);
  const u = clip.unverifiable_from;
  const end = u === null ? null : cursorAt(path, u - 1);
  const far = farEndLabel(clip.condition);
  const px = (x: number, z: number) => `${v.x(x).toFixed(1)},${v.z(z).toFixed(1)}`;
  const fwd = forwardAt(clip, frame);
  const label = fwd.kind === "value" ? `the camera is ${fmtSu(fwd.value)} su in` : "the path is not drawn here: unverifiable";
  return (
    <figure className="plan">
      <svg viewBox={`0 0 ${VIEW} ${VIEW}`} role="img" aria-label={`The tank from above. ${far[0].toUpperCase()}${far.slice(1)} ${fmtSu(plan.far_end)} su. At frame ${frame}, ${label}.`}>
        <polyline className="walls" points={wallPoints(plan, v)} />
        <line className="far-wall" x1={v.x(wall.x1)} x2={v.x(wall.x2)} y1={v.z(wall.z)} y2={v.z(wall.z)} />
        {/* beside the wall's right end, or over its end when that would run off the square (Air's longer label) */}
        {v.x(wall.x2) + 6 + (far.length + 8) * 6.5 > VIEW
          ? <text className="lbl" x={v.x(wall.x2)} y={v.z(wall.z) - 8} textAnchor="end">{far} {fmtSu(plan.far_end)} su</text>
          : <text className="lbl" x={v.x(wall.x2) + 6} y={v.z(wall.z) + 4}>{far} {fmtSu(plan.far_end)} su</text>}
        {scaleTicks(v.zMax, v.zMin).map((t) => (
          <g key={t}>
            <line className="tick" x1={TICK_GUTTER - 8} x2={TICK_GUTTER - 2} y1={v.z(t)} y2={v.z(t)} />
            <text className="lbl faint" x={TICK_GUTTER - 11} y={v.z(t) + 4} textAnchor="end">{fmtSigned(t)}</text>
          </g>
        ))}
        {runs.map((r, i) => <polyline key={i} className={r.gold ? "path gold" : "path ink"} points={r.pts.map(([x, z]) => px(x, z)).join(" ")} />)}
        {end && (
          <g className="stop">
            <line x1={v.x(end.x) - 7} x2={v.x(end.x) + 7} y1={v.z(end.z) - 2} y2={v.z(end.z) - 2} />
            <line className="stub" x1={v.x(end.x)} x2={v.x(end.x)} y1={v.z(end.z) - 2} y2={v.z(end.z) - 16} />
            <text className="lbl" x={v.x(end.x) + 10} y={v.z(end.z) - 8}>{clip.unverifiable_reason === "path lost" ? "path lost" : "trusted range ends"} · f{u}</text>
          </g>
        )}
        {cur && <circle className={cur.frozen ? "cursor frozen" : "cursor"} cx={v.x(cur.x)} cy={v.z(cur.z)} r={5} />}
        <text className="lbl faint" x={VIEW / 2} y={VIEW - 6} textAnchor="middle">su from where the camera starts</text>
      </svg>
      <figcaption className="small muted">{wallTestLimit(clip.condition)}</figcaption>
    </figure>
  );
}
