import { useState } from "react";
import type { HeatPalette } from "../data/types";
import { gradientCss } from "../lib/palette";
import { HatchSwatch } from "./HeatKey";

export const FLOOR_THUMB_W = 144, FLOOR_THUMB_H = 81;   // three quarters of call 87's 192 x 108, so the key strip is one row of 81 px (DESIGN.md, design pass)
export const FLOOR_UNOBSERVED = "not observed";

/**
 * Call 85: every heat frame opens on a pale far-end rectangle that is the mono model's own blind spot, so the per-pixel map of where
 * depth already errs on the real tank sits beside the heat. One picture for the whole recording (display only), shown in Heat and Bare.
 * Its ramp is its own (no sign), taken from clips.json; the words are the pipeline's (`floor_means`). It is never called the floor:
 * the floor is the one number D is divided by, and this is a picture of where that error lives.
 */
export function FloorThumb({ heat, src }: { heat: HeatPalette; src: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <figure className="floor-thumb" data-floor-map>
      {failed ? (
        <p className="floor-missing" role="status">The map of where mono depth errs could not be loaded.</p>
      ) : (
        <img src={src} width={FLOOR_THUMB_W} height={FLOOR_THUMB_H} decoding="async" onError={() => setFailed(true)}
          alt="A picture of where mono depth already errs on the real tank: one picture for every frame" />
      )}
      <figcaption>
        <span>{heat.floor_means}</span>
        <span className="floor-keys">
          <span className="floor-key">
            <span className="ramp-bar" style={{ background: gradientCss(heat.floor_ramp) }} aria-hidden="true" />
            <span className="floor-ends">lighter: more error</span>
          </span>
          <span className="floor-key"><HatchSwatch heat={heat} w={20} h={12} /><span>{FLOOR_UNOBSERVED}</span></span>
        </span>
      </figcaption>
    </figure>
  );
}
