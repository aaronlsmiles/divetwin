import { useId, type KeyboardEvent } from "react";
import type { Clip, HeatPalette } from "../data/types";
import { cellText, fmtD, fmtV } from "../lib/format";
import { readout, stepFrame } from "../lib/frames";
import { hatchPattern, rgbCss } from "../lib/palette";
import { D_REF, D_THRESHOLD, dAt, vAt } from "../lib/series";
import { useWidth } from "../ui/useBox";
import { makeDTrack, makeTrack, pathD, splitAtThreshold, trustedSeries, yMaxFor } from "./curve";
import "./scrubber.css";

/** The slider's id: the page's second skip link goes straight to it. */
export const SCRUBBER_ID = "frame-slider";
const D_H = 48, V_H = 14, GAP = 6;                  // the D track, the V track under it, and the space between: 68 px under a 28 px row

/** What a screen reader hears for the slider: the frame, the time, and both readings (or the word 'unverifiable'). */
export function scrubberValueText(c: Clip, f: number): string {
  return `${readout(f, c.fps)}, D ${cellText(dAt(c, f), fmtD)}, V ${cellText(vAt(c, f), fmtV)}`;
}

/**
 * One range input whose track is the D curve (docs/DESIGN.md): ink up to 3, gold above it, dashed references at D = 1 and
 * D = 3, V's curve as a second thin track, and a hatched span where verification ran out. The native thumb is hidden; the
 * cursor is drawn in the SVG so it sits exactly on the curve. Keys: arrows ±1, Shift ±12, Home, End.
 */
export function Scrubber({ clip, heat, frame, setFrame, playing, onTogglePlay, startUrl }: {
  clip: Clip; heat: HeatPalette; frame: number; setFrame: (f: number) => void;
  playing: boolean; onTogglePlay: () => void; startUrl: string;
}) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const hatchId = useId();
  const n = clip.n_frames;
  const D = trustedSeries(clip, clip.D), V = trustedSeries(clip, clip.verified);
  const yMax = yMaxFor(D);
  const td = makeDTrack(n, w, D_H, yMax), tv = makeTrack(n, w, V_H, 1);
  const segs = splitAtThreshold(D, D_THRESHOLD);
  const vSegs = splitAtThreshold(V, 2);                         // V never passes 2: one ink run per stretch of trusted frames
  const u = clip.unverifiable_from;
  const hp = hatchPattern(heat);
  const cx = td.x(frame);
  const dNow = D[frame];
  /** A scrub during Play ends Play first: otherwise the next presented frame moves the cursor straight back (End showed 120 and fell to
   *  26 within 300 ms). The pause comes before the new frame, so the seek that follows lands on the frame the reader chose. */
  const scrubTo = (f: number) => {
    if (playing) onTogglePlay();
    setFrame(f);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    const next = stepFrame(e.key, e.shiftKey, frame, n);
    if (next === null) return;
    e.preventDefault();
    scrubTo(next);
  };
  return (
    <div className="scrubber">
      <figure className="start-fig">
        <img src={startUrl} alt="The real photograph both the real tank and the dream start from" width={112} height={63} decoding="async" />
        <figcaption>the photograph both started from</figcaption>
      </figure>
      <div className="scrub-main">
        <div className="scrub-row">
          <button type="button" className="btn play" aria-pressed={playing} onClick={onTogglePlay}>
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" focusable="false">
              {playing ? <path d="M2 1h3v10H2zM7 1h3v10H7z" fill="currentColor" /> : <path d="M2 1l9 5-9 5z" fill="currentColor" />}
            </svg>
            <span>{playing ? "Pause" : "Play"}</span>
          </button>
          <output className="readout num" aria-live="off">{readout(frame, clip.fps)}</output>
          <span className="scrub-keys small">
            <span className="key-d">D</span> the curve, gold above {D_THRESHOLD} <span className="key-v">V</span> the thin line
          </span>
        </div>
        <div className="track-box" ref={ref}>
          <svg className="tracks" width={w} height={D_H + GAP + V_H} viewBox={`0 0 ${w} ${D_H + GAP + V_H}`} aria-hidden="true" focusable="false">
            <defs>
              <pattern id={hatchId} patternUnits="userSpaceOnUse" width={hp.size} height={hp.size} patternTransform={`rotate(${hp.angle})`}>
                <rect width={hp.stripe} height={hp.size} fill={rgbCss([hp.greys[0], hp.greys[0], hp.greys[0]])} />
                <rect x={hp.stripe} width={hp.stripe} height={hp.size} fill={rgbCss([hp.greys[1], hp.greys[1], hp.greys[1]])} />
              </pattern>
            </defs>
            <g className="d-track">
              {[D_REF, D_THRESHOLD].map((r) => <line key={r} className="ref" x1={0} x2={w} y1={td.y(r)} y2={td.y(r)} />)}
              {segs.map((s, i) => <path key={i} d={pathD(td, s)} className={s.gold ? "curve gold" : "curve ink"} />)}
              {clip.first_D3 !== null && <line className="departure" x1={td.x(clip.first_D3)} x2={td.x(clip.first_D3)} y1={0} y2={D_H + GAP + V_H} />}
            </g>
            <g className="v-track" transform={`translate(0 ${D_H + GAP})`}>
              <line className="ref" x1={0} x2={w} y1={tv.y(0)} y2={tv.y(0)} />
              {vSegs.map((s, i) => <path key={i} d={pathD(tv, s)} className="curve thin" />)}
            </g>
            {u !== null && (
              <rect className="hatched" x={td.x(u)} y={0} width={Math.max(0, w - td.x(u))} height={D_H + GAP + V_H} fill={`url(#${hatchId})`} />
            )}
            <line className="cursor" x1={cx} x2={cx} y1={0} y2={D_H + GAP + V_H} />
            {dNow !== null && dNow !== undefined && <circle className={dNow > D_THRESHOLD ? "dot gold" : "dot"} cx={cx} cy={td.y(dNow)} r={3.5} />}
            {/* the axis labels sit in the gutter right of the track, never under the curve; their centres are at least 11 px apart */}
            <g className="ref-labels">
              {[D_REF, D_THRESHOLD].map((r) => <text key={r} className="ref-label" x={w + 6} y={td.y(r)} dominantBaseline="middle">D = {r}</text>)}
              <text className="ref-label" x={w + 6} y={D_H + GAP + V_H / 2} dominantBaseline="middle">V</text>
            </g>
          </svg>
          <input id={SCRUBBER_ID} className="range" type="range" min={0} max={n - 1} step={1} value={frame} aria-label="Frame"
            aria-valuetext={scrubberValueText(clip, frame)}
            onChange={(e) => scrubTo(Number(e.currentTarget.value))} onKeyDown={onKeyDown} />
        </div>
      </div>
    </div>
  );
}
