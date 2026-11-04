import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { Scrubber, scrubberValueText } from "./Scrubber";
import { makeTrack } from "./curve";
import { parseClips } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";
import type { Clip } from "../data/types";

afterEach(cleanup);
const doc = parseClips(readFixtureJson("clips.json"));
const [dive, pellets, lost, calm] = doc.clips;

function setup(clip: Clip, frame: number, extra: Partial<Parameters<typeof Scrubber>[0]> = {}) {
  const setFrame = vi.fn(), onTogglePlay = vi.fn();
  const view = render(<Scrubber clip={clip} heat={doc.heat} frame={frame} setFrame={setFrame} playing={false} onTogglePlay={onTogglePlay}
    startUrl="/media/recordings/x/start.jpg" {...extra} />);
  return { ...view, setFrame, onTogglePlay, input: within(view.container).getByRole("slider", { name: "Frame" }) as HTMLInputElement };
}

describe("Scrubber", () => {
  it("is one range input over the whole clip, at the cursor", () => {
    const { input } = setup(dive, 88);
    expect(input.type).toBe("range");
    expect([input.min, input.max, input.step, input.value]).toEqual(["0", String(dive.n_frames - 1), "1", "88"]);
    expect(screen.getAllByRole("slider")).toHaveLength(1);
  });

  it("reads the frame, the time and both readings to a screen reader", () => {
    const { input } = setup(dive, 88);
    expect(input.getAttribute("aria-valuetext")).toBe(`f88 · 3.67 s, D ${dive.D[88]!.toFixed(2)}, V ${dive.verified[88]!.toFixed(2)}`);
    expect(screen.getByText("f88 · 3.67 s")).toBeTruthy();
    const u = pellets.unverifiable_from!;
    expect(scrubberValueText(pellets, u)).toMatch(/D unverifiable, V unverifiable$/);
    expect(scrubberValueText(pellets, u)).not.toMatch(/0\.00/);
  });

  it("dragging sets the frame", () => {
    const { input, setFrame } = setup(dive, 88);
    fireEvent.change(input, { target: { value: "40" } });
    expect(setFrame).toHaveBeenCalledWith(40);
  });

  it("arrows move one frame, Shift twelve, Home and End to the ends; other keys are left alone", () => {
    const { input, setFrame } = setup(dive, 50);
    const press = (key: string, shiftKey = false) => fireEvent.keyDown(input, { key, shiftKey });
    expect(press("ArrowRight")).toBe(false);                 // fireEvent returns false when preventDefault was called
    expect(setFrame).toHaveBeenLastCalledWith(51);
    press("ArrowLeft");   expect(setFrame).toHaveBeenLastCalledWith(49);
    press("ArrowRight", true); expect(setFrame).toHaveBeenLastCalledWith(62);
    press("ArrowLeft", true);  expect(setFrame).toHaveBeenLastCalledWith(38);
    press("Home");        expect(setFrame).toHaveBeenLastCalledWith(0);
    press("End");         expect(setFrame).toHaveBeenLastCalledWith(dive.n_frames - 1);
    setFrame.mockClear();
    expect(press("a")).toBe(true);
    expect(press("Tab")).toBe(true);
    expect(setFrame).not.toHaveBeenCalled();
  });

  it("the track is the D curve: gold above 3 and a departure tick for the default clip, none of either for a clip that never passes 3", () => {
    const a = setup(dive, 88);
    expect(a.container.querySelectorAll(".curve.gold").length).toBeGreaterThan(0);
    const w = 640, t = makeTrack(dive.n_frames, w, 48, 6);
    expect(Number(a.container.querySelector(".departure")!.getAttribute("x1"))).toBeCloseTo(t.x(dive.first_D3!), 5);
    a.unmount();
    const b = setup(calm, 40);
    expect(b.container.querySelectorAll(".curve.gold")).toHaveLength(0);
    expect(b.container.querySelector(".departure")).toBeNull();
    expect(b.container.querySelector(".dot.gold")).toBeNull();
  });

  it("draws the dot gold only while D is above 3", () => {
    const hi = setup(dive, 100);
    expect(dive.D[100]!).toBeGreaterThan(3);
    expect(hi.container.querySelector(".dot.gold")).not.toBeNull();
    hi.unmount();
    const lo = setup(dive, 10);
    expect(lo.container.querySelector(".dot")).not.toBeNull();
    expect(lo.container.querySelector(".dot.gold")).toBeNull();
  });

  it("dashed references at D = 1 and D = 3 sit on the D track; their labels (and V's) sit in the gutter right of it, drawn last", () => {
    const { container } = setup(dive, 88);
    const labels = [...container.querySelectorAll(".ref-labels .ref-label")];
    expect(labels.map((e) => e.textContent)).toEqual(["D = 1", "D = 3", "V"]);
    const ys = [...container.querySelectorAll(".d-track line.ref")].map((e) => Number(e.getAttribute("y1")));
    expect(ys[1]).toBeLessThan(ys[0]);
    expect(labels.slice(0, 2).map((e) => Number(e.getAttribute("y")))).toEqual(ys);         // each label on its own line's height
    for (const l of labels) expect(Number(l.getAttribute("x"))).toBeGreaterThan(640);      // past the track's right end: never under the curve
    const svg = container.querySelector("svg.tracks")!;
    expect(svg.lastElementChild!.classList.contains("ref-labels")).toBe(true);             // painted over everything else
  });
  it("the labels never collide, even when D runs to the top of the scale (centres at least 11 px apart)", () => {
    const t = makeTrack(dive.n_frames, 640, 48, 8);
    expect(t.y(1) - t.y(3)).toBeGreaterThanOrEqual(11);
  });
  it("the key row says what gold means where gold is drawn", () => {
    const { container } = setup(dive, 88);
    expect(container.querySelector(".scrub-keys")!.textContent).toContain("the curve, gold above 3");
  });

  it("hatches the span where verification ran out, from that frame to the end, and the curves stop at it", () => {
    const { container } = setup(pellets, 5);
    const rect = container.querySelector("rect.hatched")!;
    const t = makeTrack(pellets.n_frames, 640, 48, 4);
    expect(Number(rect.getAttribute("x"))).toBeCloseTo(t.x(pellets.unverifiable_from!), 5);
    expect(Number(rect.getAttribute("x")) + Number(rect.getAttribute("width"))).toBeCloseTo(640, 5);
    const xs = [...container.querySelectorAll("path.curve")].flatMap((p) => (p.getAttribute("d") ?? "").match(/-?\d+(\.\d+)?(?=,)/g) ?? []).map(Number);
    expect(Math.max(...xs)).toBeLessThanOrEqual(t.x(pellets.unverifiable_from! - 1) + 1e-6);
    expect(setup(calm, 5).container.querySelector("rect.hatched")).toBeNull();
    expect(setup(lost, 5).container.querySelector("rect.hatched")).not.toBeNull();
  });

  it("the hatch's stripes and greys are the palette's", () => {
    const { container } = setup(pellets, 5);
    const rects = [...container.querySelectorAll("pattern rect")];
    expect(rects.map((r) => r.getAttribute("width"))).toEqual(Array(2).fill(String(doc.heat.unverified_hatch.stripe_px)));
    expect(rects.map((r) => r.getAttribute("fill"))).toEqual(doc.heat.unverified_hatch.greys.map((g) => `rgb(${g},${g},${g})`));
    expect(container.querySelector("pattern")!.getAttribute("patternTransform")).toBe(`rotate(${doc.heat.unverified_hatch.angle_deg})`);
  });

  it("Play is a toggle button", () => {
    const a = setup(dive, 5);
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(a.onTogglePlay).toHaveBeenCalledTimes(1);
    a.unmount();
    setup(dive, 5, { playing: true });
    expect(screen.getByRole("button", { name: "Pause" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("a scrub during Play ends Play first and then sets the frame (otherwise the next presented frame would undo it)", () => {
    const order: string[] = [];
    const setFrame = vi.fn((f: number) => order.push(`frame ${f}`)), onTogglePlay = vi.fn(() => order.push("pause"));
    const view = render(<Scrubber clip={dive} heat={doc.heat} frame={50} setFrame={setFrame} playing onTogglePlay={onTogglePlay} startUrl="/x.jpg" />);
    const slider = within(view.container).getByRole("slider", { name: "Frame" });
    fireEvent.change(slider, { target: { value: "100" } });
    fireEvent.keyDown(slider, { key: "End" });
    fireEvent.keyDown(slider, { key: "Home" });
    expect(order).toEqual(["pause", "frame 100", "pause", `frame ${dive.n_frames - 1}`, "pause", "frame 0"]);
  });
  it("a scrub while paused does not touch Play", () => {
    const { input, setFrame, onTogglePlay } = setup(dive, 50);
    fireEvent.change(input, { target: { value: "70" } });
    fireEvent.keyDown(input, { key: "ArrowRight" });
    expect(setFrame).toHaveBeenCalledTimes(2);
    expect(onTogglePlay).not.toHaveBeenCalled();
  });
  it("shows the start photograph with its caption", () => {
    const { container } = setup(dive, 5);
    expect(container.querySelector("img")!.getAttribute("src")).toBe("/media/recordings/x/start.jpg");
    expect(screen.getByText("the photograph both started from")).toBeTruthy();
  });
});
