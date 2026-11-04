// A synthetic depth atlas for the relief tests: every cell is the real tank cell (so the dream at frame 0 sits exactly on the tank).
import { encode } from "fast-png";
import { vi } from "vitest";
import { decodePng16 } from "../data/png16";
import type { Clip, ClipsDoc } from "../data/types";
import { readFixtureBytes } from "./fixtureMedia";

export function tankBytes(doc: ClipsDoc, clip: Clip): Uint8Array {
  return readFixtureBytes(doc.recordings[clip.recording_key].tank_relief.png);
}

export function atlasBytes(clip: Clip, tank: Uint8Array): Uint8Array {
  const cell = decodePng16(tank), [w, h] = clip.relief.cell;
  const rows = Math.ceil(clip.n_frames / clip.relief.cols);
  const data = new Uint16Array(clip.relief.cols * w * rows * h);
  for (let f = 0; f < clip.n_frames; f++) {
    const r = Math.floor(f / clip.relief.cols), k = f % clip.relief.cols;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) data[(r * h + y) * clip.relief.cols * w + k * w + x] = cell.data[y * w + x];
  }
  return encode({ width: clip.relief.cols * w, height: rows * h, data, depth: 16, channels: 1 });
}

/** fetch answers the clip's atlas and tank cell from the synthetic bytes; anything else 404s. */
export function stubReliefFetch(doc: ClipsDoc, clip: Clip, base = "/media/") {
  const tank = tankBytes(doc, clip), atlas = atlasBytes(clip, tank);
  vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === base + clip.assets.relief) return new Response(atlas as BodyInit, { status: 200 });
    if (url === base + clip.assets.tank_relief) return new Response(tank as BodyInit, { status: 200 });
    return new Response("nope", { status: 404 });
  });
}
