import { describe, expect, it } from "vitest";
import { reliefFrame, unplacedText } from "./frameData";
import { atlasBytes, tankBytes } from "../test/syntheticRelief";
import { decodePng16, singleCell } from "../data/png16";
import { parseClips } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";
import type { ReliefData } from "./useRelief";

const doc = parseClips(readFixtureJson("clips.json"));
const [dive, pellets, lost] = doc.clips;

function dataFor(clip: typeof dive): ReliefData {
  const tank = tankBytes(doc, doc.clips[0]);                    // the fixture holds one real tank cell; the clips share it here
  return { clip: clip.clip, atlas: decodePng16(atlasBytes(clip, tank)), tank: singleCell(decodePng16(tank), clip.relief.depth_scale) };
}

describe("reliefFrame", () => {
  it("at frame 0 a dream that sees exactly the tank has no gap anywhere (identity pose, same ray)", () => {
    const f = reliefFrame(dive, doc.heat, dataFor(dive), 0);
    expect(f.dream).not.toBeNull();
    const finite = Array.from(f.gap!).filter(Number.isFinite);
    expect(finite.length).toBeGreaterThan(10_000);
    expect(Math.max(...finite.map(Math.abs))).toBeLessThan(1e-3);
    expect(f.real.indices.length).toBeGreaterThan(0);
    expect(f.dream!.colours).toHaveLength(f.dream!.positions.length);
  });
  it("later the same dream, moved forward by the path, no longer sits on the tank (the gap is the dream leaving it)", () => {
    const f = reliefFrame(dive, doc.heat, dataFor(dive), 100);
    const finite = Array.from(f.gap!).filter(Number.isFinite);
    expect(finite.length).toBeGreaterThan(0);
    expect(Math.max(...finite.map(Math.abs))).toBeGreaterThan(0.05);
  });
  it("past where verification ran out nothing is placed", () => {
    const f = reliefFrame(pellets, doc.heat, dataFor(pellets), pellets.unverifiable_from!);
    expect(f.dream).toBeNull();
    expect(f.gap).toBeNull();
    expect(f.real.positions.length).toBeGreaterThan(0);
  });
  it("says why when the dream is not placed: from which frame, the reason, and that only the real tank is drawn", () => {
    const u = pellets.unverifiable_from!;
    expect(unplacedText(pellets, u - 1)).toBeNull();
    expect(reliefFrame(pellets, doc.heat, dataFor(pellets), u - 1).dream).not.toBeNull();
    expect(unplacedText(pellets, u)).toBe(`From frame ${u}: the dream passed the recording's trusted range (${Math.round(pellets.trusted_travel_su!)} su). Only the real tank is drawn; the dream is not placed.`);
    expect(unplacedText(lost, lost.unverifiable_from! + 3)).toBe(`From frame ${lost.unverifiable_from}: the camera path was lost. Only the real tank is drawn; the dream is not placed.`);
    expect(unplacedText(dive, 120)).toBeNull();
  });
});
