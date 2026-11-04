import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { frameFromMediaTime, useNativePlay, useSeek } from "./sync";
import { timeFor } from "../lib/frames";

/** A video that records what is done to it, with a presented-frame callback the test fires by hand. */
function fake(ready = 4, withVfc = true) {
  const v = document.createElement("video");
  Object.defineProperty(v, "readyState", { value: ready, configurable: true });
  let t = 0;
  const seeks: number[] = [];
  Object.defineProperty(v, "currentTime", { get: () => t, set: (x: number) => { t = x; seeks.push(x); }, configurable: true });
  const play = vi.fn(() => Promise.resolve()), pause = vi.fn();
  v.play = play; v.pause = pause;
  let cb: VideoFrameRequestCallback | null = null;
  if (withVfc) {
    v.requestVideoFrameCallback = (f) => { cb = f; return 1; };
    v.cancelVideoFrameCallback = vi.fn();
  } else {
    (v as { requestVideoFrameCallback?: unknown }).requestVideoFrameCallback = undefined;       // older browsers: the property is missing
  }
  return { v, seeks, play, pause, setTime: (x: number) => { t = x; }, present: (mediaTime: number) => { const f = cb; cb = null; f?.(0, { mediaTime } as VideoFrameCallbackMetadata); } };
}

describe("frameFromMediaTime", () => {
  it("a presented picture's media time is n / fps; the frame is the nearest, clamped to the clip", () => {
    expect(frameFromMediaTime(88 / 24, 24, 121)).toBe(88);
    expect(frameFromMediaTime(88 / 24 + 0.004, 24, 121)).toBe(88);
    expect(frameFromMediaTime(-1, 24, 121)).toBe(0);
    expect(frameFromMediaTime(99, 24, 121)).toBe(120);
  });
});

describe("useSeek: scrubbing seeks every pane to the middle of the same frame", () => {
  it("sets currentTime on each ready video to (frame + 0.5) / fps", () => {
    const a = fake(), b = fake(), c = fake();
    renderHook(() => useSeek([{ current: a.v }, { current: b.v }, { current: c.v }], 88, 24, "k"));
    for (const x of [a, b, c]) expect(x.seeks).toEqual([timeFor(88, 24)]);
  });
  it("a video that is not ready yet gets the latest frame when its metadata arrives, not the one it was first asked for", () => {
    const a = fake(0);
    const { rerender } = renderHook(({ f }) => useSeek([{ current: a.v }], f, 24, "k"), { initialProps: { f: 10 } });
    rerender({ f: 30 });
    Object.defineProperty(a.v, "readyState", { value: 1, configurable: true });
    a.v.dispatchEvent(new Event("loadedmetadata"));
    expect(a.seeks).toEqual([timeFor(30, 24)]);
  });
  it("does not seek while playing: seeking per frame at 24 Hz is what starves the decoder", () => {
    const a = fake();
    const { rerender } = renderHook(({ f, on }) => useSeek([{ current: a.v }], f, 24, "k", on), { initialProps: { f: 5, on: false } });
    rerender({ f: 6, on: false }); rerender({ f: 7, on: false });
    expect(a.seeks).toEqual([]);
    rerender({ f: 7, on: true });
    expect(a.seeks).toEqual([timeFor(7, 24)]);                  // on pause, every pane (the hidden one too) lands on the frame
  });
});

describe("useNativePlay: Play plays", () => {
  let real: ReturnType<typeof fake>, heat: ReturnType<typeof fake>, gen: ReturnType<typeof fake>;
  let setFrame: Mock<(f: number) => void>, setPlaying: Mock<(p: boolean) => void>;
  beforeEach(() => { real = fake(); heat = fake(); gen = fake(); setFrame = vi.fn<(f: number) => void>(); setPlaying = vi.fn<(p: boolean) => void>(); });
  afterEach(() => vi.useRealTimers());

  const run = (props: Partial<{ playing: boolean; frame: number; view: "heat" | "gen" }> = {}) =>
    renderHook((p: { playing: boolean; frame: number; view: "heat" | "gen" }) => useNativePlay({
      real: { current: real.v }, dreams: { heat: { current: heat.v }, gen: { current: gen.v } }, view: p.view, clipKey: "k", frame: p.frame,
      n: 121, fps: 24, playing: p.playing, setFrame, setPlaying }), { initialProps: { playing: true, frame: 10, view: "heat" as const, ...props } });

  it("plays the real pane and the visible dream view natively, from the cursor's frame; the hidden view is not played", () => {
    run();
    expect(real.play).toHaveBeenCalledTimes(1);
    expect(heat.play).toHaveBeenCalledTimes(1);
    expect(gen.play).not.toHaveBeenCalled();
    expect(real.seeks).toEqual([timeFor(10, 24)]);
    expect(heat.seeks).toEqual([timeFor(10, 24)]);
    expect(gen.seeks).toEqual([]);                              // the hidden view seeks on pause or a switch only
  });
  it("the cursor follows the real pane's presented frames (requestVideoFrameCallback), whatever the wall clock says", () => {
    run();
    real.setTime(14 / 24); real.present(14 / 24);
    expect(setFrame).toHaveBeenLastCalledWith(14);
    real.setTime(15 / 24); real.present(15 / 24);
    expect(setFrame).toHaveBeenLastCalledWith(15);
  });
  it("a dream view that drifts more than a frame from the real pane is seeked back; within a frame it is left alone", () => {
    run();
    heat.seeks.length = 0;
    real.setTime(20 / 24); heat.setTime(20 / 24 + 0.5 / 24); real.present(20 / 24);
    expect(heat.seeks).toEqual([]);
    heat.setTime(20 / 24 + 3 / 24); real.present(20 / 24);
    expect(heat.seeks).toEqual([20 / 24]);
  });
  it("stops at the last frame", () => {
    run();
    real.present(119 / 24);
    expect(setPlaying).not.toHaveBeenCalled();
    real.present(120 / 24);
    expect(setPlaying).toHaveBeenCalledWith(false);
  });
  it("stops when the real pane ends, on the last frame", () => {
    run();
    real.v.dispatchEvent(new Event("ended"));
    expect(setFrame).toHaveBeenLastCalledWith(120);
    expect(setPlaying).toHaveBeenCalledWith(false);
  });
  it("Play on the last frame starts again from 0", () => {
    run({ frame: 120 });
    expect(setFrame).toHaveBeenCalledWith(0);
    expect(real.seeks).toEqual([timeFor(0, 24)]);
  });
  it("a presented picture that arrives after Play was ended does not move the cursor", () => {
    const { rerender } = run();
    setFrame.mockClear();
    rerender({ playing: false, frame: 120, view: "heat" });
    real.present(26 / 24);                                       // the late picture of a scrub's race: End showed 120, then 26
    expect(setFrame).not.toHaveBeenCalled();
  });
  it("watches for presented pictures only after the seek to the start has landed (Play from the last frame must not read the picture it was left on and stop)", () => {
    Object.defineProperty(real.v, "seeking", { value: true, configurable: true });
    run({ frame: 120 });
    real.present(120 / 24);                                      // no callback is registered yet: nothing happens
    expect(setPlaying).not.toHaveBeenCalled();
    expect(setFrame).toHaveBeenCalledWith(0);                    // (the restart itself)
    setFrame.mockClear();
    Object.defineProperty(real.v, "seeking", { value: false, configurable: true });
    real.v.dispatchEvent(new Event("seeked"));
    real.present(1 / 24);                                        // now the first picture counts
    expect(setFrame).toHaveBeenLastCalledWith(1);
    expect(setPlaying).not.toHaveBeenCalled();
  });
  it("tolerates a play() that returns nothing (jsdom before its stub, an old browser)", () => {
    real.v.play = (() => undefined) as unknown as typeof real.v.play;
    heat.v.play = (() => undefined) as unknown as typeof heat.v.play;
    expect(() => run()).not.toThrow();
    expect(setPlaying).not.toHaveBeenCalled();
  });
  it("pausing pauses every video (the cursor's frame is then seeked into all three by useSeek)", () => {
    const { rerender } = run();
    rerender({ playing: false, frame: 30, view: "heat" });
    for (const x of [real, heat, gen]) expect(x.pause).toHaveBeenCalled();
  });
  it("switching the dream view while playing plays the new one from the real pane's time and stops the old one", () => {
    const { rerender } = run();
    real.setTime(40 / 24);
    rerender({ playing: true, frame: 40, view: "gen" });
    expect(gen.seeks).toEqual([40 / 24]);
    expect(gen.play).toHaveBeenCalledTimes(1);
    expect(heat.pause).toHaveBeenCalled();
  });
  it("where requestVideoFrameCallback is missing it reads the real pane's currentTime each animation frame", () => {
    vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame"] });
    real = fake(4, false);
    run();
    real.setTime(7 / 24);
    act(() => { vi.advanceTimersByTime(40); });
    expect(setFrame).toHaveBeenCalledWith(7);
  });
});
