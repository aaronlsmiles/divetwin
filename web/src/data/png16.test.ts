import { encode } from "fast-png";
import { describe, expect, it } from "vitest";
import { atlasCell, decodePng16, singleCell } from "./png16";
import { readFixtureBytes, readFixtureJson } from "../test/fixtureMedia";

const grey16 = (width: number, height: number, f: (x: number, y: number) => number) => {
  const data = new Uint16Array(width * height);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) data[y * width + x] = f(x, y);
  return encode({ width, height, data, depth: 16, channels: 1 });
};

describe("PNG16 depth cells (decoded by fast-png, never by canvas)", () => {
  it("round-trips 16-bit values exactly (a canvas would squash them to 8 bits)", () => {
    const png = decodePng16(grey16(3, 2, (x, y) => 40000 + 1000 * y + x));
    expect([png.width, png.height]).toEqual([3, 2]);
    expect(Array.from(png.data)).toEqual([40000, 40001, 40002, 41000, 41001, 41002]);
  });

  it("refuses an 8-bit or colour PNG, which would silently read as nonsense depth", () => {
    const eight = encode({ width: 2, height: 2, data: new Uint8Array(4), depth: 8, channels: 1 });
    expect(() => decodePng16(eight)).toThrow(/16-bit/);
    const rgb = encode({ width: 1, height: 1, data: new Uint16Array(3), depth: 16, channels: 3 });
    expect(() => decodePng16(rgb)).toThrow(/grey/);
  });

  it("reads the real tank relief: the size the data says, no invalid cells, depths in a plausible range", () => {
    const doc = readFixtureJson("clips.json");
    const meta = doc.recordings["freshwater-basicEnhance"].tank_relief;
    const png = decodePng16(readFixtureBytes(meta.png));
    expect([png.width, png.height]).toEqual(meta.cell);
    const z = singleCell(png, meta.depth_scale);
    expect(z).toHaveLength(meta.cell[0] * meta.cell[1]);
    expect(z.filter(Number.isNaN)).toHaveLength(meta.invalid);
    const far = doc.recordings["freshwater-basicEnhance"].far_end;
    const max = Math.max(...z);
    expect(max).toBeGreaterThan(far * 0.8);
    expect(max).toBeLessThan(far * 1.6);
  });

  it("stored 0 is no depth (NaN), never zero su", () => {
    const png = decodePng16(grey16(2, 1, (x) => (x === 0 ? 0 : 1600)));
    const z = singleCell(png, 16);
    expect(Number.isNaN(z[0])).toBe(true);
    expect(z[1]).toBe(100);
  });

  it("finds frame f in the atlas: cols per row, left to right, top to bottom", () => {
    const cols = 3, cell: [number, number] = [4, 2];
    const frames = 7;                                              // 3 rows; the last row is part empty
    const atlas = decodePng16(grey16(cols * cell[0], 3 * cell[1], (x, y) => {
      const f = Math.floor(y / cell[1]) * cols + Math.floor(x / cell[0]);
      return f < frames ? 160 * (f + 1) : 0;                         // 10 su * (frame + 1)
    }));
    for (const f of [0, 2, 3, 6]) {
      const z = atlasCell(atlas, { cols, cell, depth_scale: 16 }, f);
      expect(z).toHaveLength(8);
      expect(new Set(z)).toEqual(new Set([10 * (f + 1)]));
    }
    expect(() => atlasCell(atlas, { cols, cell, depth_scale: 16 }, 9)).toThrow(/frame 9/);
  });
});
