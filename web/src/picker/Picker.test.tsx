import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Picker } from "./Picker";
import { lengthsFor, resolve, valuesOf } from "./options";
import { parseClips } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";
import type { Clip } from "../data/types";

afterEach(cleanup);
const doc = parseClips(readFixtureJson("clips.json"));
const [dive, , , calm] = doc.clips;
// The structure of the real 35: 5 recordings x 2 engines x 3 prompts at 5 s, plus a 10 s D dive per recording on Gen-4.5.
// Built from the fixture's clips by changing only the dimensions (the page logic reads nothing else).
const grid: Clip[] = [];
for (const condition of ["air", "freshwater", "freshwater-basicEnhance", "saltwater", "saltwater-pellets"])
  for (const engine of ["gen45", "wan22"]) for (const prompt of ["D", "B", "N"]) {
    grid.push({ ...calm, clip: `${condition}__${engine}__${prompt}__5s`, condition, engine, prompt, seconds: 5 });
    if (engine === "gen45" && prompt === "D") grid.push({ ...calm, clip: `${condition}__${engine}__${prompt}__10s`, condition, engine, prompt, seconds: 10 });
  }

describe("clip options", () => {
  it("the grid has 35 clips; dimensions list in file order", () => {
    expect(grid).toHaveLength(35);
    expect(valuesOf(grid, "engine")).toEqual(["gen45", "wan22"]);
    expect(valuesOf(grid, "prompt")).toEqual(["D", "B", "N"]);
  });
  it("a 10 s length exists only for Gen-4.5 prompt D", () => {
    const d5 = grid.find((c) => c.clip === "air__gen45__D__5s")!;
    expect(lengthsFor(grid, d5)).toEqual([5, 10]);
    expect(lengthsFor(grid, grid.find((c) => c.clip === "air__wan22__D__5s")!)).toEqual([5]);
  });
  it("changing one thing keeps the rest", () => {
    const cur = grid.find((c) => c.clip === "air__gen45__D__10s")!;
    expect(resolve(grid, cur, { condition: "saltwater" }).clip).toBe("saltwater__gen45__D__10s");
    expect(resolve(grid, cur, { seconds: 5 }).clip).toBe("air__gen45__D__5s");
  });
  it("a combination that does not exist drops to the nearest that does: never a dead end", () => {
    const cur = grid.find((c) => c.clip === "air__gen45__D__10s")!;
    expect(resolve(grid, cur, { prompt: "B" }).clip).toBe("air__gen45__B__5s");
    expect(resolve(grid, cur, { engine: "wan22" }).clip).toBe("air__wan22__D__5s");
  });
});

describe("Picker", () => {
  const pick = (cur: Clip, list: Clip[] = doc.clips) => { const onPick = vi.fn(); render(<Picker clips={list} clip={cur} onPick={onPick} />); return onPick; };
  it("three segmented controls with short names, the current one on", () => {
    pick(dive, grid.map((c) => (c.clip === dive.clip ? dive : c)));
    expect((screen.getByLabelText("Freshwater, enhanced") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Gen-4.5") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("N") as HTMLInputElement).checked).toBe(true);
  });
  it("choosing an option asks for the resolved clip", () => {
    const onPick = pick({ ...calm, clip: "air__gen45__D__5s" }, grid);
    fireEvent.click(screen.getByLabelText("Wan 2.2"));
    expect(onPick).toHaveBeenCalledWith("air__wan22__D__5s");
    fireEvent.click(screen.getByLabelText("Saltwater, pellets"));
    expect(onPick).toHaveBeenLastCalledWith("saltwater-pellets__gen45__D__5s");
  });
  it("the length switch is there only where a 10 s dive exists", () => {
    pick({ ...calm, clip: "air__gen45__D__5s" }, grid);
    expect(screen.getByRole("group", { name: "Length" })).toBeTruthy();
    cleanup();
    pick({ ...calm, clip: "air__wan22__N__5s", engine: "wan22", prompt: "N" }, grid);
    expect(screen.queryByRole("group", { name: "Length" })).toBeNull();
  });
  it("is usable by keyboard: every option is a native radio", () => {
    pick({ ...calm, clip: "air__gen45__D__5s" }, grid);
    expect(document.querySelectorAll('input[type="radio"]').length).toBe(5 + 2 + 3 + 2);
  });
  it("on a phone the three controls are three selects", () => {
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("640"), media: q, addEventListener() {}, removeEventListener() {} }));
    const onPick = pick({ ...calm, clip: "air__gen45__D__5s" }, grid);
    expect(screen.getAllByRole("combobox")).toHaveLength(3);
    fireEvent.change(screen.getByLabelText("Engine"), { target: { value: "wan22" } });
    expect(onPick).toHaveBeenCalledWith("air__wan22__D__5s");
    vi.unstubAllGlobals();
  });
});
