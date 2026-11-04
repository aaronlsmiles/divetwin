import { useId } from "react";
import type { HeatPalette } from "../data/types";
import { D_REF, D_THRESHOLD } from "../lib/series";
import { gradientCss, hatchPattern, rgbCss } from "../lib/palette";

/** A hatched swatch drawn from the palette's own numbers (angle, stripe width, the two greys). */
export function HatchSwatch({ heat, w = 28, h = 16 }: { heat: HeatPalette; w?: number; h?: number }) {
  const id = useId();
  const p = hatchPattern(heat);
  return (
    <svg className="swatch" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true" focusable="false">
      <defs>
        <pattern id={id} patternUnits="userSpaceOnUse" width={p.size} height={p.size} patternTransform={`rotate(${p.angle})`}>
          <rect width={p.stripe} height={p.size} fill={rgbCss([p.greys[0], p.greys[0], p.greys[0]])} />
          <rect x={p.stripe} width={p.stripe} height={p.size} fill={rgbCss([p.greys[1], p.greys[1], p.greys[1]])} />
        </pattern>
      </defs>
      <rect width={w} height={h} fill={`url(#${id})`} />
    </svg>
  );
}

/** The heat's two ramps in words and swatches, each on one line, entirely from clips.json's palette (heat.palette_json). */
export function HeatRamps({ heat, floor }: { heat: HeatPalette; floor: number }) {
  // D is the mean gap over the verified pixels divided by the floor, so on the ramp D = 1 sits at the floor and D = 3 at three times it
  const d3 = 3 * floor;
  return (
    <div className="ramps">
      <div className="ramp">
        <span className="ramp-bar" style={{ background: gradientCss(heat.positive) }} aria-hidden="true" />
        <span className="ramp-text">{heat.positive_means}</span>
      </div>
      <div className="ramp">
        <span className="ramp-bar" style={{ background: gradientCss(heat.negative) }} aria-hidden="true" />
        <span className="ramp-text">{heat.negative_means}</span>
      </div>
      <p className="ramp-scale">
        darker: no gap; lighter: a bigger gap (relative), clipped at {heat.clip}. D {D_REF} is a mean gap of {floor.toFixed(3)}, D {D_THRESHOLD} is {d3.toFixed(3)}{d3 > heat.clip ? ", past the clip" : ""}.
      </p>
    </div>
  );
}

/** The heat's marks: the hatch (unverified) and the outline (a tracked moving object), from the same palette. */
export function HeatMarks({ heat }: { heat: HeatPalette }) {
  return (
    <>
      <li>
        <HatchSwatch heat={heat} />
        <span><strong>{heat.unverified}</strong>: {heat.unverified_reasons.join("; ")}</span>
      </li>
      <li>
        <span className="swatch outline" style={{ outlineColor: rgbCss(heat.outline.rgb), outlineWidth: heat.outline.width_px }} aria-hidden="true" />
        <span>{heat.outlined}</span>
      </li>
    </>
  );
}
