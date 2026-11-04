// The relief's intrinsics against the real runs/assets: skipped, saying so, when it is not there (as data/realContract.test.ts).
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseClips } from "../data/load";
import { fallbackIntrinsics } from "./surfaces";

const ASSETS = process.env.DIVETWIN_ASSETS ?? join(dirname(fileURLToPath(import.meta.url)), "../../../runs/assets");
const have = existsSync(join(ASSETS, "clips.json"));

describe.skipIf(!have)("the real clips' relief blocks", () => {
  const doc = have ? parseClips(JSON.parse(readFileSync(join(ASSETS, "clips.json"), "utf8"))) : (undefined as never);

  it("every clip's relief block carries the cell intrinsics (pipeline task C0), equal within 0.001 to the pinned fallback: the fallback is the pipeline's calibration", () => {
    for (const c of doc.clips) {
      const f = fallbackIntrinsics(c.relief.box);
      for (const k of ["fx", "fy", "cx", "cy"] as const) {
        expect(typeof c.relief[k], `${c.clip} relief.${k}`).toBe("number");
        expect(Math.abs(c.relief[k]! - f[k]), `${c.clip} relief.${k}`).toBeLessThan(1e-3);
      }
    }
    expect(doc.clips.some((c) => c.relief.box[1] > 0), "at least one clip has a box that is not the whole frame").toBe(true);
  });
});
