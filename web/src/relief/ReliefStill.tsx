import { useEffect, useRef } from "react";
import type { HeatPalette } from "../data/types";
import { gapColours } from "./surfaces";
import { GRID_H, GRID_W } from "./surfaces";

/** The relief as a still: the gap at this frame as a picture, one cell per pixel, drawn without WebGL. */
export function ReliefStill({ gap, heat, label }: { gap: Float32Array | null; heat: HeatPalette; label: string }) {   // `label` leads with what the colour is
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(GRID_W, GRID_H);
    const rgb = gap ? gapColours(gap, heat) : null;
    for (let i = 0; i < GRID_W * GRID_H; i++) {
      img.data[4 * i] = rgb ? rgb[3 * i] * 255 : heat.unseen_rgb[0];
      img.data[4 * i + 1] = rgb ? rgb[3 * i + 1] * 255 : heat.unseen_rgb[1];
      img.data[4 * i + 2] = rgb ? rgb[3 * i + 2] * 255 : heat.unseen_rgb[2];
      img.data[4 * i + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
  }, [gap, heat]);
  return <canvas ref={ref} className="relief-still" width={GRID_W} height={GRID_H} role="img" aria-label={label} />;
}
