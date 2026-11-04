import { decode } from "fast-png";

/** A single-channel 16-bit PNG, as pipeline/assets.py writes depth (stored = round(su * depth_scale); 0 = no depth). */
export interface Gray16 { width: number; height: number; data: Uint16Array }
export interface AtlasMeta { cols: number; cell: [number, number]; depth_scale: number }

export function decodePng16(bytes: ArrayBuffer | Uint8Array): Gray16 {
  const png = decode(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes));
  if (png.depth !== 16) throw new Error(`expected a 16-bit PNG, got ${png.depth}-bit`);
  if (png.channels !== 1) throw new Error(`expected a grey PNG (1 channel), got ${png.channels}`);
  return { width: png.width, height: png.height, data: png.data as Uint16Array };
}

/** Depth in su, row-major; NaN where the pipeline stored 0 (no depth). */
export function singleCell(png: Gray16, depthScale: number): Float32Array {
  const out = new Float32Array(png.data.length);
  for (let i = 0; i < out.length; i++) out[i] = png.data[i] === 0 ? NaN : png.data[i] / depthScale;
  return out;
}

/** Frame `f` of a packed atlas: `cols` cells per row, left to right, top to bottom (assets.pack_atlas). */
export function atlasCell(atlas: Gray16, meta: AtlasMeta, f: number): Float32Array {
  const [w, h] = meta.cell;
  const rows = Math.floor(atlas.height / h);
  if (!Number.isInteger(f) || f < 0 || f >= rows * meta.cols) throw new Error(`frame ${f} is outside the atlas (${rows * meta.cols} cells)`);
  const r = Math.floor(f / meta.cols), k = f % meta.cols;
  const out = new Float32Array(w * h);
  for (let y = 0; y < h; y++) {
    const row = (r * h + y) * atlas.width + k * w;
    for (let x = 0; x < w; x++) {
      const v = atlas.data[row + x];
      out[y * w + x] = v === 0 ? NaN : v / meta.depth_scale;
    }
  }
  return out;
}

export async function loadGray16(url: string): Promise<Gray16> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return decodePng16(await r.arrayBuffer());
}
