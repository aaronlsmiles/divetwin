import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { DEFAULT_CLIP, parseLocation, serialise, URL_SETTLE_MS, useDiveState } from "./urlState";
import { parseClips } from "../data/load";
import { findingFrame } from "../lib/finding";
import { readFixtureJson } from "../test/fixtureMedia";

const doc = parseClips(readFixtureJson("clips.json"));
const [dive, pellets, , calm] = doc.clips;

beforeEach(() => window.history.replaceState(null, "", "/"));
afterEach(() => window.history.replaceState(null, "", "/"));

describe("parseLocation: ?clip=<id>&f=<frame>", () => {
  it("opens on the default clip at its departure frame when the URL says nothing", () => {
    expect(DEFAULT_CLIP).toBe("freshwater-basicEnhance__gen45__N__5s");
    expect(parseLocation("", doc)).toEqual({ clip: dive.clip, frame: 88 });
  });
  it("reads a clip and a frame", () => {
    expect(parseLocation(`?clip=${pellets.clip}&f=7`, doc)).toEqual({ clip: pellets.clip, frame: 7 });
  });
  it("a clip with no f opens on its own finding, not on frame 0", () => {
    const peak = calm.D.indexOf(Math.max(...calm.D.filter((d): d is number => d !== null)));
    expect(parseLocation(`?clip=${calm.clip}`, doc)).toEqual({ clip: calm.clip, frame: peak });
  });
  it("an unknown clip falls back to the default; a bad frame is clamped or ignored", () => {
    expect(parseLocation("?clip=nope&f=3", doc).clip).toBe(dive.clip);
    expect(parseLocation(`?clip=${dive.clip}&f=9999`, doc).frame).toBe(dive.n_frames - 1);
    expect(parseLocation(`?clip=${dive.clip}&f=-4`, doc).frame).toBe(0);
    expect(parseLocation(`?clip=${dive.clip}&f=abc`, doc).frame).toBe(88);
    expect(parseLocation(`?clip=${dive.clip}&f=12.7`, doc).frame).toBe(88);
  });
  it("if the default clip is not in the file, the first clip opens (never a blank page)", () => {
    const other = { ...doc, clips: doc.clips.slice(1) };
    expect(parseLocation("", other).clip).toBe(pellets.clip);
  });
  it("serialises the state back to the same query", () => {
    expect(serialise({ clip: dive.clip, frame: 88 })).toBe(`?clip=${dive.clip}&f=88`);
    expect(parseLocation(serialise({ clip: lostId(), frame: 30 }), doc)).toEqual({ clip: lostId(), frame: 30 });
  });
});
const lostId = () => doc.clips[2].clip;

describe("useDiveState", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("starts from the URL; a clip change adds a history entry", () => {
    window.history.replaceState(null, "", `/?clip=${calm.clip}&f=5`);
    const { result } = renderHook(() => useDiveState(doc));
    expect(result.current.clip.clip).toBe(calm.clip);
    expect(result.current.frame).toBe(5);
    const len = window.history.length;
    act(() => result.current.setClip(pellets.clip));
    expect(result.current.clip.clip).toBe(pellets.clip);
    expect(result.current.frame).toBe(findingFrame(pellets));
    expect(window.location.search).toBe(`?clip=${pellets.clip}&f=${findingFrame(pellets)}`);
    expect(window.history.length).toBe(len + 1);
  });

  it("scrubbing updates the page at once and the URL once the frame has been still (Play moves it 24 times a second)", () => {
    window.history.replaceState(null, "", `/?clip=${calm.clip}&f=5`);
    const spy = vi.spyOn(window.history, "replaceState");
    const { result } = renderHook(() => useDiveState(doc));
    for (const f of [6, 7, 8, 9, 40]) act(() => result.current.setFrame(f));
    expect(result.current.frame).toBe(40);
    expect(spy).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(URL_SETTLE_MS - 1); });
    expect(spy).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(2); });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(window.location.search).toBe(`?clip=${calm.clip}&f=40`);
    spy.mockRestore();
  });

  it("clamps setFrame to the clip", () => {
    const { result } = renderHook(() => useDiveState(doc));
    act(() => result.current.setFrame(10_000));
    expect(result.current.frame).toBe(dive.n_frames - 1);
    act(() => result.current.setFrame(-5));
    expect(result.current.frame).toBe(0);
  });

  it("follows the back button, and drops a pending URL write so it cannot undo the move", () => {
    const { result } = renderHook(() => useDiveState(doc));
    act(() => result.current.setClip(calm.clip));
    act(() => result.current.setFrame(70));
    act(() => {
      window.history.replaceState(null, "", `/?clip=${dive.clip}&f=3`);
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    act(() => { vi.advanceTimersByTime(1000); });
    expect(result.current.clip.clip).toBe(dive.clip);
    expect(result.current.frame).toBe(3);
    expect(window.location.search).toBe(`?clip=${dive.clip}&f=3`);
  });
});
