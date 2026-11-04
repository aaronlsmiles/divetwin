import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { ClipTable, crumbOf } from "./ClipTable";
import { rowsOf, sortRows, sortValue } from "./rows";
import { parseClips } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";

afterEach(cleanup);
const doc = parseClips(readFixtureJson("clips.json"));
const [dive, pellets, lost, calm] = doc.clips;
const rows = rowsOf(doc.clips);
const bodyRows = () => within(document.querySelector("tbody") as HTMLElement).getAllByRole("row");
const cellsOf = (tr: HTMLElement, col: string) => (tr.querySelector(`[data-col="${col}"]`) as HTMLElement).textContent;

describe("ClipTable", () => {
  it("has a row for every clip, in the file's order", () => {
    render(<ClipTable clips={doc.clips} current={dive.clip} onPick={() => {}} />);
    expect(bodyRows()).toHaveLength(doc.clips.length);
    expect(bodyRows().map((r) => cellsOf(r, "recording"))).toEqual(["Freshwater, enhanced", "Saltwater, pellets", "Air", "Air"]);
  });
  it("D and V at 5 s are the data's, to two places", () => {
    render(<ClipTable clips={doc.clips} current={dive.clip} onPick={() => {}} />);
    const r = bodyRows()[0];
    expect(cellsOf(r, "d5")).toBe(dive.D_at["5"]!.toFixed(2));
    expect(cellsOf(r, "v5")).toBe(dive.V_at["5"]!.toFixed(2));
    expect(cellsOf(r, "departure")).toBe("f88");
    expect(cellsOf(r, "d10")).toBe("–");                                  // a 5 s clip has no 10 s
  });
  it("a cell past a cap says 'unverifiable', never the 0.00 the data holds; a clip with no departure has a grey dash", () => {
    render(<ClipTable clips={doc.clips} current={dive.clip} onPick={() => {}} />);
    const p = bodyRows()[1];
    expect(pellets.V_at["5"]).toBe(0);
    expect(cellsOf(p, "v5")).toBe("unverifiable");
    expect(cellsOf(p, "d5")).toBe("unverifiable");
    expect(cellsOf(p, "departure")).toBe("–");
    expect(p.querySelector('[data-col="departure"] .dash')).not.toBeNull();
    expect(document.querySelector("tbody")!.textContent).not.toContain("0.00");
    expect(lost.unverifiable_reason).toBe("path lost");
    expect(cellsOf(bodyRows()[2], "v5")).toBe("unverifiable");              // the lost path, too
  });
  it("each row's button is named by the whole clip, not just the recording (35 'Air' buttons would be indistinguishable)", () => {
    render(<ClipTable clips={doc.clips} current={dive.clip} onPick={() => {}} />);
    expect(bodyRows().map((r) => within(r).getByRole("button").getAttribute("aria-label"))).toEqual([
      "Freshwater, enhanced · Gen-4.5 · prompt N · 5 s", "Saltwater, pellets · Gen-4.5 · prompt N · 5 s", "Air · Wan 2.2 · prompt N · 5 s", "Air · Gen-4.5 · prompt D · 5 s"]);
    expect(screen.getByRole("button", { name: "Air · Gen-4.5 · prompt D · 5 s" })).toBeTruthy();
  });
  it("a D above 3 is set in 600 weight, never gold (gold stays on the stage, the plan and the lead figure)", () => {
    const { container } = render(<ClipTable clips={doc.clips} current={doc.clips[0].clip} onPick={() => {}} />);
    const cells = [...container.querySelectorAll('td[data-col="d5"], td[data-col="d10"]')] as HTMLElement[];
    const over = cells.filter((td) => Number(td.textContent) > 3);
    expect(over.length).toBeGreaterThan(0);
    for (const td of cells) expect(td.classList.contains("over")).toBe(Number(td.textContent) > 3);
    expect(container.innerHTML).not.toMatch(/gold/);
  });
  it("travel is in su, rounded", () => {
    render(<ClipTable clips={doc.clips} current={dive.clip} onPick={() => {}} />);
    expect(cellsOf(bodyRows()[0], "travel")).toBe(`${Math.round(dive.travel)} su`);
  });
  it("choosing a row, by click or by its button, loads that clip; the current row is marked", () => {
    const onPick = vi.fn();
    render(<ClipTable clips={doc.clips} current={calm.clip} onPick={onPick} />);
    expect(bodyRows()[3].getAttribute("aria-current")).toBe("true");
    fireEvent.click(bodyRows()[1]);
    expect(onPick).toHaveBeenLastCalledWith(pellets.clip);
    fireEvent.click(within(bodyRows()[0]).getByRole("button"));
    expect(onPick).toHaveBeenLastCalledWith(dive.clip);
    expect(onPick).toHaveBeenCalledTimes(2);
  });
  it("sorts by a column, flips on a second press, and a third restores the file's order; aria-sort says which", () => {
    render(<ClipTable clips={doc.clips} current={dive.clip} onPick={() => {}} />);
    const th = screen.getByRole("columnheader", { name: /^Travel/ });
    fireEvent.click(within(th).getByRole("button"));
    expect(th.getAttribute("aria-sort")).toBe("ascending");
    const travel = bodyRows().map((r) => cellsOf(r, "travel"));
    expect(travel).toEqual([...doc.clips].sort((a, b) => a.travel - b.travel).map((c) => `${Math.round(c.travel)} su`));
    fireEvent.click(within(screen.getByRole("columnheader", { name: /^Travel/ })).getByRole("button"));
    expect(screen.getByRole("columnheader", { name: /^Travel/ }).getAttribute("aria-sort")).toBe("descending");
    fireEvent.click(within(screen.getByRole("columnheader", { name: /^Travel/ })).getByRole("button"));
    expect(bodyRows().map((r) => cellsOf(r, "recording"))[0]).toBe("Freshwater, enhanced");
  });
});

describe("sortRows", () => {
  it("cells with no number (unverifiable, a dash) sort last whichever way it runs", () => {
    for (const dir of ["asc", "desc"] as const) {
      const sorted = sortRows(rows, "d5", dir);
      const nulls = sorted.map((r) => sortValue(r, "d5") === null);
      expect(nulls.lastIndexOf(false)).toBeLessThan(nulls.indexOf(true));
    }
  });
  it("is stable: ties keep the file's order", () => {
    const tie = sortRows(rows, "prompt", "asc").filter((r) => r.clip.prompt === "N").map((r) => r.order);
    expect(tie).toEqual([...tie].sort((a, b) => a - b));
  });
  it("departure sorts the clips with one first, the rest after", () => {
    expect(sortRows(rows, "departure", "asc")[0].clip.clip).toBe(dive.clip);
  });
});

describe("the phone row's breadcrumb (task 4.6)", () => {
  it("never lets a wrapped line start with a separator: every \u00b7 is held to the word before it, and 'prompt N' and '5 s' stay whole", () => {
    for (const c of doc.clips) {
      const crumb = crumbOf(c);
      expect(crumb.replace(/\u00a0/g, " ").replace(/\u2060/g, "")).toBe(` \u00b7 ${c.engine === "gen45" ? "Gen-4.5" : "Wan 2.2"} \u00b7 prompt ${c.prompt} \u00b7 ${c.seconds} s`);
      expect(crumb).not.toMatch(/ \u00b7/);                       // a plain space before a "\u00b7" would be a place to break
      expect(crumb).toMatch(/\u00a0\u00b7/);
      if (c.engine === "gen45") expect(crumb).toContain("Gen\u2060-\u20604.5");                 // a hyphen is a place to break: held
      expect(crumb).toContain(`prompt\u00a0${c.prompt}`);
      expect(crumb).toMatch(/\d\u00a0s$/);
      expect(crumb.slice(1)).not.toMatch(/\w \w[^ ]* \u00b7|\w \w$/);          // no plain space left inside a unit (the only plain spaces follow a \u00b7)
    }
  });
});
