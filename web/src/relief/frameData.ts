import type { Clip, HeatPalette } from "../data/types";
import { cellIntrinsics, cellPoints, gapColours, gapField, gridIndices, placePoints, poseAt, toScene } from "./surfaces";
import { dreamCell, type ReliefData } from "./useRelief";
import { reasonText } from "../lib/format";
import { isUnverifiable } from "../lib/series";

export interface ReliefFrame {
  real: { positions: Float32Array; indices: Uint32Array };
  dream: { positions: Float32Array; colours: Float32Array; indices: Uint32Array } | null;   // null: nothing is placed at this frame
  gap: Float32Array | null;
}

/** Everything the relief draws at one frame: the real tank's surface, and the dream's placed, coloured by its gap. */
export function reliefFrame(clip: Clip, heat: HeatPalette, d: ReliefData, f: number): ReliefFrame {
  const k = cellIntrinsics(clip);
  const real = { positions: toScene(cellPoints(d.tank, k)), indices: gridIndices(d.tank) };
  const pose = poseAt(clip, f);
  if (!pose) return { real, dream: null, gap: null };
  const z = dreamCell(clip, d, f);
  const world = placePoints(cellPoints(z, k), pose);
  const gap = gapField(world, d.tank, k);
  return { real, dream: { positions: toScene(world), colours: gapColours(gap, heat), indices: gridIndices(z) }, gap };
}

/** Past a cap or a loss the path is never extrapolated, so the dream is not placed (reliefFrame's `dream: null`): the caption and the
 *  label say from which frame, and why. Null where the dream is placed. */
export const unplacedText = (clip: Clip, f: number): string | null =>
  isUnverifiable(clip, f) ? `From frame ${clip.unverifiable_from}: ${reasonText(clip)}. Only the real tank is drawn; the dream is not placed.` : null;
