import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { App } from "../App";
import { clearCache, parseClips } from "../data/load";
import { allowedFor, bandFigures, numerals, pageText, STATIC_NUMERALS, staticText, STRUCTURAL } from "./facts";
import { tally } from "../lib/tally";
import { FIXTURE_IDS, readFixtureJson, stubFixtureFetch } from "./fixtureMedia";
import { clipTitle, finding, findingFrame } from "../lib/finding";

const doc = parseClips(readFixtureJson("clips.json"));
beforeEach(() => { clearCache(); window.history.replaceState(null, "", "/"); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const open = async (id: string, f?: number) => {
  stubFixtureFetch("/media/");
  window.history.replaceState(null, "", `/?clip=${id}${f === undefined ? "" : `&f=${f}`}`);
  const view = render(<App />);
  const clip = doc.clips.find((c) => c.clip === id)!;
  await screen.findByRole("heading", { level: 1, name: clipTitle(clip) });
  await waitFor(() => expect(view.container.querySelector("svg[role=img] .path, .plan .path")).not.toBeNull());   // the plan has loaded
  return { view, clip };
};

describe("the page renders every clip in the fixture", () => {
  for (const id of FIXTURE_IDS) {
    it(id, async () => {
      const { view, clip } = await open(id);
      expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(clipTitle(clip));
      expect(view.container.querySelector(".finding")!.textContent).toBe(finding(clip));
      expect((screen.getByRole("slider", { name: "Frame" }) as HTMLInputElement).value).toBe(String(findingFrame(clip)));
      expect(document.querySelectorAll("video")).toHaveLength(3);
      for (const c of doc.clips) expect(screen.getAllByRole("button", { name: new RegExp(`^${c.condition === "air" ? "Air" : ".+"}`) }).length).toBeGreaterThan(0);
      expect(view.container.querySelectorAll(".clip-table tbody tr")).toHaveLength(doc.clips.length);
      expect(view.container.querySelectorAll(".clip-table tbody tr.is-active")).toHaveLength(1);
      expect(view.container.querySelector(".numbers")).not.toBeNull();
      expect(view.container.querySelector(".relief")).not.toBeNull();
      expect(pageText(view.container)).not.toMatch(/NaN|undefined|\bnull\b|Infinity/);
    });
  }

  it("choosing another clip in the table loads it, and the URL follows", async () => {
    const { view } = await open(FIXTURE_IDS[0]);
    const row = view.container.querySelectorAll(".clip-table tbody tr")[1] as HTMLElement;
    fireEvent.click(within(row).getByRole("button"));
    await screen.findByRole("heading", { level: 1, name: clipTitle(doc.clips[1]) });
    expect(window.location.search).toContain(`clip=${doc.clips[1].clip}`);
  });
});

describe("the findings band on the page (hub call 92)", () => {
  it("sits between the title row and the stage, and says the fixture's tally", async () => {
    const { view } = await open(FIXTURE_IDS[0]);
    const band = view.container.querySelector(".band")!;
    expect(band.previousElementSibling!.classList.contains("title-row")).toBe(true);
    const after = [...view.container.querySelectorAll(".title-row, .band, .stage")];
    expect(after.map((e) => e.className.split(" ")[0])).toEqual(["title-row", "band", "stage"]);
    expect(within(band as HTMLElement).getAllByRole("button").map((b) => b.textContent)).toEqual(["1 leaves the tank for good", "1 stays under 3", "2 can't be checked to the end"]);
  });

  it("a count filters the clip table to its clips and moves focus to the line that says so; Show all brings every clip back", async () => {
    const { view } = await open(FIXTURE_IDS[0]);
    const scrolled = vi.fn(), was = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrolled;
    afterEach(() => { Element.prototype.scrollIntoView = was; });
    fireEvent.click(screen.getByRole("button", { name: /^2 can't be checked to the end/ }));
    const line = await screen.findByText(/^Showing the 2 clips that can't be checked to the end/);
    await waitFor(() => expect(document.activeElement).toBe(line.closest("[tabindex]")));
    expect(scrolled).toHaveBeenCalled();
    const rows = () => [...view.container.querySelectorAll(".clip-table tbody tr")].map((r) => within(r as HTMLElement).getByRole("button").getAttribute("aria-label"));
    expect(rows()).toEqual([clipTitle(doc.clips[1]), clipTitle(doc.clips[2])]);
    fireEvent.click(screen.getByRole("button", { name: `Show all ${doc.clips.length}` }));
    expect(rows()).toHaveLength(doc.clips.length);
    expect(screen.queryByText(/^Showing the/)).toBeNull();
  });
});

describe("no figure on the page is hand-typed", () => {
  const cases: [string, number][] = [
    [FIXTURE_IDS[0], 88], [FIXTURE_IDS[0], 0], [FIXTURE_IDS[0], 120],
    [FIXTURE_IDS[1], 5], [FIXTURE_IDS[1], 90],               // pellets: before and past the cap
    [FIXTURE_IDS[2], 30], [FIXTURE_IDS[2], 100],             // air Wan N: before and after the path is lost
    [FIXTURE_IDS[3], 60],
  ];
  for (const [id, f] of cases) {
    it(`${id} at frame ${f}: every numeral traces to clips.json, or to a named threshold`, async () => {
      const { view, clip } = await open(id, f);
      const allowed = allowedFor(doc, clip, f);
      const unknown = [...new Set(numerals(pageText(view.container)))].filter((n) => !allowed.has(n));
      expect(unknown, `numerals with no source in the data: ${unknown.join(", ")}`).toEqual([]);
    });
  }
  it("the figures in the statement and the credits are only model names, versions, licences, the DOI and the two thresholds (an explicit list)", async () => {
    const { view } = await open(FIXTURE_IDS[0], 88);
    const found = [...new Set(numerals(staticText(view.container)))];
    const unknown = found.filter((n) => !(n in STATIC_NUMERALS));
    expect(unknown, `numerals in the static prose with no entry in STATIC_NUMERALS: ${unknown.join(", ")}`).toEqual([]);
    for (const why of Object.values(STATIC_NUMERALS)) expect(why.length).toBeGreaterThan(8);
  });
  it("the spoken words count too: aria-labels, aria-valuetext and alt are scanned with the visible text", async () => {
    const { view, clip } = await open(FIXTURE_IDS[0], 88);
    const text = pageText(view.container);
    expect(text).toContain("f88 · 3.67 s, D");                       // the scrubber's aria-valuetext
    expect(text).toContain("The tank from above.");                  // the plan view's aria-label
    const planted = document.createElement("div");
    planted.setAttribute("aria-label", "a spoken 9191 here");
    view.container.querySelector(".numbers")!.appendChild(planted);
    const unknown = numerals(pageText(view.container)).filter((n) => !allowedFor(doc, clip, 88).has(n));
    expect(unknown).toEqual(["9191"]);
  });
  it("the structural list is short and each entry says where it comes from", () => {
    expect(Object.keys(STRUCTURAL).sort()).toEqual(["1", "12", "200", "3"]);
    for (const why of Object.values(STRUCTURAL)) expect(why.length).toBeGreaterThan(10);
  });
  it("the findings band is scanned too: its counts and its V trace to the data by the facts file's own arithmetic, and a typed count is caught", async () => {
    const { view, clip } = await open(FIXTURE_IDS[0], 88);
    const band = view.container.querySelector(".band") as HTMLElement;
    const inBand = numerals(pageText(band));
    expect(inBand.length).toBeGreaterThan(3);
    expect(bandFigures(doc)).toEqual(["1", "2", "1", "1.00"]);            // departs, unchecked, under; the departing Gen-4.5 clip's lowest V
    for (const t of tally(doc.clips)) expect(bandFigures(doc)).toContain(String(t.n));
    const typed = document.createElement("span");
    typed.textContent = "7 leave the tank for good";
    band.querySelector(".tally")!.appendChild(typed);
    const unknown = numerals(pageText(view.container)).filter((n) => !allowedFor(doc, clip, 88).has(n));
    expect(unknown).toEqual(["7"]);
  });
  it("and the check can fail: a figure the data does not hold is caught", async () => {
    const { view, clip } = await open(FIXTURE_IDS[0], 88);
    const h = document.createElement("p");
    h.textContent = "a typed 4242 here";
    view.container.querySelector(".numbers")!.appendChild(h);
    const unknown = numerals(pageText(view.container)).filter((n) => !allowedFor(doc, clip, 88).has(n));
    expect(unknown).toEqual(["4242"]);
  });
});
