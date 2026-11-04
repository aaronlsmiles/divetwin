import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { realCaption, Stage } from "./Stage";
import { parseClips } from "../data/load";
import { timeFor } from "../lib/frames";
import { gradientCss } from "../lib/palette";
import { FLOOR_UNOBSERVED } from "./FloorThumb";
import { readFixtureJson } from "../test/fixtureMedia";

const doc = parseClips(readFixtureJson("clips.json"));
const dive = doc.clips[0];
const seeks = new Map<HTMLMediaElement, number[]>();
const proto = HTMLMediaElement.prototype;
const saved = { time: Object.getOwnPropertyDescriptor(proto, "currentTime"), ready: Object.getOwnPropertyDescriptor(proto, "readyState") };

beforeEach(() => {
  seeks.clear();
  Object.defineProperty(proto, "readyState", { get: () => 4, configurable: true });
  Object.defineProperty(proto, "currentTime", {
    get() { return (this as any)._t ?? 0; },
    set(v: number) { (this as any)._t = v; seeks.set(this, [...(seeks.get(this) ?? []), v]); },
    configurable: true,
  });
});
afterEach(() => {
  cleanup();
  if (saved.time) Object.defineProperty(proto, "currentTime", saved.time);
  if (saved.ready) Object.defineProperty(proto, "readyState", saved.ready);
});

const renderStage = (frame: number, playing = false) => render(<Stage doc={doc} clip={dive} frame={frame} base="/media/" playing={playing} setFrame={vi.fn()} setPlaying={vi.fn()}><div data-testid="scrubber-slot" /></Stage>);
const videos = (c: HTMLElement) => Object.fromEntries([...c.querySelectorAll("video")].map((v) => [v.dataset.paneVideo, v])) as Record<"real" | "heat" | "gen", HTMLVideoElement>;

describe("Stage", () => {
  it("shows the real tank and the dream side by side, from the clip's own files", () => {
    const { container } = renderStage(88);
    const v = videos(container);
    expect(v.real.getAttribute("src")).toBe(`/media/${dive.assets.real}`);
    expect(v.heat.getAttribute("src")).toBe(`/media/${dive.assets.heat}`);
    expect(v.gen.getAttribute("src")).toBe(`/media/${dive.assets.gen}`);
    expect(screen.getByRole("heading", { name: "The real tank, rebuilt from stereo" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "The dream" })).toBeTruthy();
    expect(screen.getByTestId("scrubber-slot")).toBeTruthy();
    for (const el of Object.values(v)) { expect(el.muted).toBe(true); expect(el.hasAttribute("controls")).toBe(false); }
  });

  it("every pane seeks to the middle of the same frame", () => {
    const { container, rerender } = renderStage(88);
    const v = videos(container);
    for (const el of Object.values(v)) expect(seeks.get(el)).toEqual([timeFor(88, dive.fps)]);
    rerender(<Stage doc={doc} clip={dive} frame={89} base="/media/" playing={false} setFrame={vi.fn()} setPlaying={vi.fn()}><div /></Stage>);
    for (const el of Object.values(v)) expect(seeks.get(el)).toEqual([timeFor(88, dive.fps), timeFor(89, dive.fps)]);
  });

  it("the dream is Heat by default; Bare swaps the pane without unmounting either video", () => {
    const { container } = renderStage(88);
    const v = videos(container);
    expect(v.heat.hidden).toBe(false);
    expect(v.gen.hidden).toBe(true);
    const sw = within(screen.getByRole("group", { name: "Dream view" }));
    expect((sw.getByLabelText("Heat") as HTMLInputElement).checked).toBe(true);
    fireEvent.click(sw.getByLabelText("Bare"));
    expect(videos(container).heat).toBe(v.heat);               // the same elements: nothing remounted
    expect(v.heat.hidden).toBe(true);
    expect(v.gen.hidden).toBe(false);
    expect(screen.getByText(/The engine's own clip, unedited/)).toBeTruthy();
  });

  it("the real pane's caption carries the unseen grey from the palette", () => {
    const { container } = renderStage(88);
    const sw = container.querySelector(".key-strip .key-real .swatch.grey") as HTMLElement;
    const [r, g, b] = doc.heat.unseen_rgb;
    expect(sw.style.background).toBe(`rgb(${r}, ${g}, ${b})`);
    const real = container.querySelector(".key-real") as HTMLElement;
    expect(within(real).getByText(/grey: no real camera looked here/)).toBeTruthy();
    expect(videos(container).real.getAttribute("aria-describedby")).toBe(real.id);           // the real pane names its key line
  });

  it("past a cap or a loss the real pane's caption says the grey also covers where the dream can no longer be checked", () => {
    const [, pellets, lost] = doc.clips;
    const plain = "grey: no real camera looked here", past = "grey: no real camera looked here, or past where the dream can be checked";
    expect(realCaption(dive, 120)).toBe(plain);
    expect(realCaption(pellets, pellets.unverifiable_from! - 1)).toBe(plain);
    expect(realCaption(pellets, pellets.unverifiable_from!)).toBe(past);
    expect(realCaption(lost, lost.lost_from! + 2)).toBe(past);
    cleanup();
    const { container } = render(<Stage doc={doc} clip={pellets} frame={pellets.unverifiable_from! + 5} base="/media/" playing={false} setFrame={vi.fn()} setPlaying={vi.fn()}><div /></Stage>);
    expect((container.querySelector(".key-real") as HTMLElement).textContent!.trim()).toBe(past);
  });

  it("the heat key is built from the palette in clips.json: both ramps, the hatch, the outline, the words", () => {
    const { container } = renderStage(88);
    const key = within(screen.getByRole("group", { name: "Key to the stage" }));
    expect(key.getByText(doc.heat.positive_means)).toBeTruthy();
    expect(key.getByText(doc.heat.negative_means)).toBeTruthy();
    expect(key.getByText(doc.heat.outlined)).toBeTruthy();
    expect(key.getByText(doc.heat.unverified)).toBeTruthy();
    expect(container.textContent).toContain(doc.heat.unverified_reasons[0]);
    const bars = [...container.querySelectorAll(".key-strip .ramps .ramp-bar")] as HTMLElement[];
    expect(bars).toHaveLength(2);
    const probe = document.createElement("div");
    probe.style.background = gradientCss(doc.heat.positive);
    expect(bars[0].style.background).toBe(probe.style.background);
    const o = container.querySelector(".swatch.outline") as HTMLElement;
    expect(o.style.outlineWidth).toBe(`${doc.heat.outline.width_px}px`);
    const greys = [...container.querySelectorAll(".marks pattern rect")].map((r) => r.getAttribute("fill"));
    expect(greys).toEqual(doc.heat.unverified_hatch.greys.map((g) => `rgb(${g},${g},${g})`));
  });

  it("while playing, nothing seeks per frame: the panes play on their own clocks", () => {
    const { container, rerender } = renderStage(88, true);
    const v = videos(container);
    const before = seeks.get(v.real)?.length ?? 0;
    rerender(<Stage doc={doc} clip={dive} frame={89} base="/media/" playing setFrame={vi.fn()} setPlaying={vi.fn()}><div /></Stage>);
    rerender(<Stage doc={doc} clip={dive} frame={90} base="/media/" playing setFrame={vi.fn()} setPlaying={vi.fn()}><div /></Stage>);
    expect(seeks.get(v.real)?.length ?? 0).toBe(before);
    expect(seeks.get(v.gen) ?? []).toEqual([]);                           // the hidden view is never touched while playing
  });

  describe("the map of where mono depth errs (call 85), beside the key", () => {
    const rec = doc.recordings["freshwater-basicEnhance"];
    it("is the recording's own preview at 144 x 81, last in the key strip, after the marks and the ramps", () => {
      const { container } = renderStage(88);
      const img = container.querySelector("[data-floor-map] img") as HTMLImageElement;
      expect(img.getAttribute("src")).toBe(`/media/${rec.floor_map.preview}`);
      expect([img.width, img.height]).toEqual([144, 81]);
      const row = container.querySelector(".key-strip")!;
      expect([...row.children].map((c) => c.className)).toEqual(["marks", "ramps", "floor-thumb"]);
    });
    it("says what it is in the pipeline's words, and never calls it the floor", () => {
      const { container } = renderStage(88);
      const fig = container.querySelector("[data-floor-map]") as HTMLElement;
      expect(within(fig).getByText(doc.heat.floor_means)).toBeTruthy();
      expect(doc.heat.floor_means).toMatch(/display only, the same for every frame/);
      expect(fig.textContent!.toLowerCase()).not.toContain("floor");
      expect(fig.querySelector("img")!.getAttribute("alt")!.toLowerCase()).not.toContain("floor");
    });
    it("draws its ramp from the palette's floor_ramp, and the hatch swatch says 'not observed'", () => {
      const { container } = renderStage(88);
      const fig = container.querySelector("[data-floor-map]") as HTMLElement;
      const probe = document.createElement("div");
      probe.style.background = gradientCss(doc.heat.floor_ramp);
      expect((fig.querySelector(".ramp-bar") as HTMLElement).style.background).toBe(probe.style.background);
      expect(within(fig).getByText(FLOOR_UNOBSERVED)).toBeTruthy();
      expect(fig.querySelectorAll("pattern rect")).toHaveLength(2);
    });
    it("shows the next recording's map again after a failed one (the thumbnail is keyed by its file)", () => {
      const { container, rerender } = renderStage(88);
      fireEvent.error(container.querySelector("[data-floor-map] img")!);
      expect(container.querySelector("[data-floor-map] img")).toBeNull();
      const other = doc.clips[1];                                 // saltwater, pellets: another recording, another preview
      rerender(<Stage doc={doc} clip={other} frame={5} base="/media/" playing={false} setFrame={vi.fn()} setPlaying={vi.fn()}><div /></Stage>);
      expect(container.querySelector("[data-floor-map] img")!.getAttribute("src")).toBe(`/media/${doc.recordings[other.recording_key].floor_map.preview}`);
    });
    it("is there in Bare as well as Heat", () => {
      const { container } = renderStage(88);
      fireEvent.click(within(screen.getByRole("group", { name: "Dream view" })).getByLabelText("Bare"));
      expect(container.querySelector(".key-strip [data-floor-map]")).not.toBeNull();
      expect(container.querySelector(".key-strip .ramps")).toBeNull();
      expect(container.querySelectorAll(".key-strip .marks li")).toHaveLength(1);              // the real pane's grey stays; the heat's marks go
    });
    it("a map that fails to load is a line of text, not a broken picture", () => {
      const { container } = renderStage(88);
      fireEvent.error(container.querySelector("[data-floor-map] img")!);
      expect(container.querySelector("[data-floor-map] img")).toBeNull();
      expect(screen.getByRole("status").textContent).toMatch(/could not be loaded/);
    });
  });

  it("reads in the order it is seen: both panes, the scrubber straight under them, then the key strip", () => {
    const { container } = renderStage(88);
    const stage = container.querySelector(".stage")!;
    expect([...stage.children].map((c) => c.className || (c as HTMLElement).dataset.testid)).toEqual(["panes", "scrubber-slot", "key-strip"]);
    expect(videos(container).heat.getAttribute("aria-describedby")).toBe(container.querySelector(".key-strip")!.id);
  });

  it("past a cap or a loss the real pane says why on its flat grey, and the way back goes to the last checked frame", () => {
    const [, pellets] = doc.clips, u = pellets.unverifiable_from!;
    const setFrame = vi.fn();
    const at = (f: number) => render(<Stage doc={doc} clip={pellets} frame={f} base="/media/" playing={false} setFrame={setFrame} setPlaying={vi.fn()}><div /></Stage>);
    at(u - 1);
    expect(document.querySelector(".pane-notice")).toBeNull();
    cleanup();
    const { container } = at(u + 10);
    const notice = container.querySelector('[data-pane="real"] .pane-frame .pane-notice') as HTMLElement;
    expect(notice.getAttribute("role")).toBe("status");
    expect(notice.textContent).toContain(`From frame ${u}, nothing here can be checked: the dream passed the recording's trusted range`);
    fireEvent.click(within(notice).getByRole("button", { name: "Back to the last checked frame" }));
    expect(setFrame).toHaveBeenCalledWith(u - 1);
    expect(container.querySelector('[data-pane="dream"] .pane-notice')).toBeNull();               // one notice, on the real pane's grey only
  });

  it("a clip that fails to load says so, in words, once", () => {
    const { container } = renderStage(88);
    fireEvent.error(videos(container).real);
    expect(screen.getByRole("alert").textContent).toMatch(/A clip could not be loaded \(real\)/);
  });
});
