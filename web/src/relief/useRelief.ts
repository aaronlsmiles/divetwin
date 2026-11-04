import { useEffect, useState } from "react";
import type { Clip } from "../data/types";
import { mediaUrl } from "../data/media";
import { atlasCell, loadGray16, singleCell, type Gray16 } from "../data/png16";

export interface ReliefData { clip: string; atlas: Gray16; tank: Float32Array }

/** The clip's depth atlas and its tank cell, loaded once the panel is wanted. */
export function useReliefData(clip: Clip, base: string, wanted: boolean) {
  const [data, setData] = useState<ReliefData | "error" | null>(null);
  useEffect(() => {
    if (!wanted) return;
    let live = true;
    setData(null);
    Promise.all([loadGray16(mediaUrl(clip.assets.relief, base)), loadGray16(mediaUrl(clip.assets.tank_relief, base))])
      .then(([atlas, tank]) => live && setData({ clip: clip.clip, atlas, tank: singleCell(tank, clip.relief.depth_scale) }), () => live && setData("error"));
    return () => { live = false; };
  }, [clip, base, wanted]);
  return data;
}

export const dreamCell = (clip: Clip, d: ReliefData, f: number): Float32Array =>
  atlasCell(d.atlas, { cols: clip.relief.cols, cell: clip.relief.cell, depth_scale: clip.relief.depth_scale }, f);
