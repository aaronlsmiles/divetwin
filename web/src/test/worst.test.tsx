// Task 4.6, break-ui: the worst realistic data (src/test/worst.ts) through the whole page. The layout side (overflow, wrapping, clipping)
// is e2e/worst.spec.ts on real files; this file holds what text and markup can show: no NaN, no "0.00" for what cannot be verified,
// every fault named in words, nothing thrown.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { App } from "../App";
import { clearCache, parseClips } from "../data/load";
import { FIXTURE_IDS, fixturePath, readFixtureJson } from "./fixtureMedia";
import { dead, LONG_NAME_60, longName, MISSING, offScale } from "./worst";
import { pageText } from "./facts";
import { clipTitle, finding } from "../lib/finding";

const [DEFAULT, PELLETS, AIR_WAN, AIR_D] = FIXTURE_IDS;
const base = readFixtureJson("clips.json");
const pathOf = (id: string) => readFixtureJson(`clips/${id}/path.json`);

/** A fetch that answers from the fixtures, except where the case says otherwise: a mutated clips.json, mutated paths, 404s. */
function stub(opts: { doc?: unknown; paths?: Record<string, unknown>; missing?: RegExp[] } = {}) {
  vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
    const url = String(input);
    const json = (x: unknown) => new Response(JSON.stringify(x), { status: 200, headers: { "content-type": "application/json" } });
    if (opts.missing?.some((m) => m.test(url))) return new Response("not found", { status: 404 });
    if (url === "/media/clips.json" && opts.doc) return json(opts.doc);
    const m = /^\/media\/clips\/([^/]+)\/path\.json$/.exec(url);
    if (m && opts.paths?.[m[1]]) return json(opts.paths[m[1]]);
    try {
      const bytes = readFileSync(fixturePath(url.slice("/media/".length)));
      return new Response(bytes, { status: 200, headers: { "content-type": url.endsWith(".json") ? "application/json" : url.endsWith(".png") ? "image/png" : "application/octet-stream" } });
    } catch { return new Response("not found", { status: 404 }); }
  });
}

beforeEach(() => { clearCache(); window.history.replaceState(null, "", "/"); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function open(doc: unknown, id: string, f?: number) {
  window.history.replaceState(null, "", `/?clip=${id}${f === undefined ? "" : `&f=${f}`}`);
  const clip = parseClips(doc).clips.find((c) => c.clip === id)!;
  const view = render(<App />);
  await screen.findByRole("heading", { level: 1, name: clipTitle(clip) });
  await waitFor(() => expect(view.container.querySelector(".plan svg")).not.toBeNull());      // the plan has loaded (or this fails: it must draw)
  return { view, clip };
}

/** No attribute the page draws with holds NaN, Infinity or undefined (an SVG path with NaN is invisible, which is the quiet way to break). */
function badDrawing(root: HTMLElement): string[] {
  const attrs = ["d", "points", "x", "y", "cx", "cy", "x1", "x2", "y1", "y2", "width", "height", "viewBox", "transform", "style"];
  return [...root.querySelectorAll("*")].flatMap((e) => attrs.flatMap((a) => {
    const v = e.getAttribute(a);
    return v !== null && /NaN|Infinity|undefined/.test(v) ? [`${e.tagName}[${a}]=${v.slice(0, 60)}`] : [];
  }));
}
const clean = (text: string) => expect(text).not.toMatch(/NaN|undefined|\bnull\b|Infinity/);

describe("worst case: a D off the scale", () => {
  const doc = offScale(base, DEFAULT, 40);
  it("is drawn on the top edge, said as 40.00 in the readout, the lead figure and the table, and is gold", async () => {
    stub({ doc });
    const { view } = await open(doc, DEFAULT, 110);
    clean(pageText(view.container));
    expect(badDrawing(view.container)).toEqual([]);
    expect(view.container.querySelector(".numbers .lead")!.textContent).toBe("40.00");
    expect(view.container.querySelector(".numbers .lead")!.getAttribute("data-gold")).toBe("true");
    expect(screen.getByRole("slider", { name: "Frame" }).getAttribute("aria-valuetext")).toContain("D 40.00");
    expect(view.container.querySelector(".clip-table tbody tr.is-active")!.textContent).toContain("40.00");
    // the curve is clamped at the axis top, never past the track
    const top = [...view.container.querySelectorAll(".curve.gold")].flatMap((p) => (p.getAttribute("d") ?? "").match(/,([\d.]+)/g) ?? []).map((s) => Number(s.slice(1)));
    expect(Math.min(...top)).toBeGreaterThanOrEqual(2);
  });
});

describe("worst case: a recording name of 60 characters", () => {
  const doc = longName(base, "freshwater-basicEnhance", LONG_NAME_60);
  it("is exactly 60 characters", () => expect(LONG_NAME_60).toHaveLength(60));
  it("shows whole in the title, the picker, the table and the document title, and no NaN anywhere", async () => {
    stub({ doc });
    const { view, clip } = await open(doc, DEFAULT);
    expect(clip.condition).toBe(LONG_NAME_60);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(`${LONG_NAME_60} · Gen-4.5 · prompt N · 5 s`);
    expect(screen.getByRole("radio", { name: LONG_NAME_60 })).toBeTruthy();
    expect(view.container.querySelector(".clip-table tbody tr.is-active .row-btn")!.textContent).toBe(LONG_NAME_60);
    expect(document.title).toContain(LONG_NAME_60);
    clean(pageText(view.container));
    expect(badDrawing(view.container)).toEqual([]);
    expect(view.container.querySelector(".finding")!.textContent).toBe(finding(clip));
  });
});

describe("worst case: a missing relief atlas and a missing floor preview", () => {
  it("each says so in words on its own panel, and nothing else on the page changes", async () => {
    stub({ missing: MISSING });
    const { view } = await open(base, DEFAULT);
    await waitFor(() => expect(view.container.querySelector(".relief")!.textContent).toContain("The depth atlas could not be loaded."));
    expect(view.container.querySelector(".relief [role=alert]")).not.toBeNull();
    expect(view.container.querySelector(".relief")!.textContent).toContain("Everything else on the page still works");
    expect(view.container.querySelector(".relief")!.textContent).not.toMatch(/A still:|WebGL/);          // no note about a picture that is not there
    // the floor preview is an image: its error event is what the page listens for (jsdom does not load images, so fire it)
    const img = view.container.querySelector("[data-floor-map] img")!;
    img.dispatchEvent(new Event("error"));
    await waitFor(() => expect(view.container.querySelector("[data-floor-map] .floor-missing")!.textContent).toContain("could not be loaded"));
    expect(view.container.querySelector("[data-floor-map] figcaption")).not.toBeNull();   // the key stays
    clean(pageText(view.container));
    expect(view.container.querySelector(".numbers")).not.toBeNull();
    expect(view.container.querySelector(".plan .path, svg[role=img] .path")).not.toBeNull();   // the plan view is untouched
  });
});

describe("worst case: a clip that cannot be verified from frame 0", () => {
  for (const reason of ["path lost", "travel cap"] as const) {
    it(`${reason}: never a number, never 0.00, the finding and every cell say unverifiable`, async () => {
      const w = dead(base, pathOf(AIR_D), AIR_D, reason);
      stub({ doc: w.doc, paths: { [AIR_D]: w.path } });
      const { view, clip } = await open(w.doc, AIR_D);
      const text = pageText(view.container);
      clean(text);
      expect(badDrawing(view.container)).toEqual([]);
      // the only 0.00 that may be on the page is a time (f0 · 0.00 s); a D or a V of 0.00 would be a lie about what was not measured
      expect(text.replace(/f\d+ · \d+\.\d{2} s/g, "")).not.toMatch(/\b0\.00\b/);
      expect(view.container.querySelector(".finding")!.textContent).toMatch(/^Verification ran out at frame 0 \(0\.0 s\): /);
      expect(view.container.querySelector(".finding")!.textContent).toBe(finding(clip));
      expect(view.container.querySelector(".numbers .lead")!.textContent).toBe("unverifiable");
      expect(view.container.querySelector(".numbers .lead")!.getAttribute("data-gold")).toBeNull();
      expect(screen.getByRole("slider", { name: "Frame" }).getAttribute("aria-valuetext")).toBe("f0 · 0.00 s, D unverifiable, V unverifiable");
      const row = view.container.querySelector(".clip-table tbody tr.is-active")!;
      expect(row.querySelector('[data-col="d5"]')!.textContent).toBe("unverifiable");
      expect(row.querySelector('[data-col="v5"]')!.textContent).toBe("unverifiable");
      // the real pane says why it is flat from frame 0, and offers no way back (there is no checked frame)
      const notice = view.container.querySelector('[data-pane="real"] .pane-notice')!;
      expect(notice.textContent).toContain("From frame 0, nothing here can be checked");
      expect(notice.querySelector("button")).toBeNull();
    });
  }
});

describe("worst case: everything at once", () => {
  it("a long name, a D of 40, a dead clip and both 404s on one page, on every frame of the default clip, throws nothing", async () => {
    let doc: any = longName(offScale(base, DEFAULT, 40), "freshwater-basicEnhance", LONG_NAME_60);
    const w = dead(doc, pathOf(PELLETS), PELLETS, "travel cap"); doc = w.doc;
    stub({ doc, paths: { [PELLETS]: w.path }, missing: MISSING });
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    for (const [id, f] of [[DEFAULT, 0], [DEFAULT, 120], [PELLETS, 0], [AIR_WAN, 100]] as const) {
      cleanup(); clearCache();
      const { view } = await open(doc, id, f);
      clean(pageText(view.container));
      expect(badDrawing(view.container)).toEqual([]);
    }
    expect(errors.mock.calls.map((c) => String(c[0]).slice(0, 80))).toEqual([]);
    errors.mockRestore();
  });
});
