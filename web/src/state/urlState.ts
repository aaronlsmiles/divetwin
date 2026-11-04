import { useCallback, useEffect, useRef, useState } from "react";
import type { Clip, ClipsDoc } from "../data/types";
import { clampFrame } from "../lib/frames";
import { findingFrame } from "../lib/finding";

/** The page opens on the film's clip (call 81), its cursor parked on the departure. */
export const DEFAULT_CLIP = "freshwater-basicEnhance__gen45__N__5s";

export interface DiveState { clip: string; frame: number }

export function parseLocation(search: string, doc: ClipsDoc): DiveState {
  const q = new URLSearchParams(search);
  const byId = (id: string | null) => doc.clips.find((c) => c.clip === id);
  const clip = byId(q.get("clip")) ?? byId(DEFAULT_CLIP) ?? doc.clips[0];
  const f = q.get("f");
  const frame = f !== null && /^-?\d+$/.test(f) ? clampFrame(Number(f), clip.n_frames) : findingFrame(clip);
  return { clip: clip.clip, frame };
}

export const serialise = (s: DiveState): string => `?clip=${s.clip}&f=${s.frame}`;

/** Browsers cap history.replaceState (Safari throws past 100 calls in 30 s), and Play moves the frame 24 times a second: so the URL
 *  follows the frame only once it has been still for this long. */
export const URL_SETTLE_MS = 250;

/** The page's one piece of state, kept in the URL: ?clip=<id>&f=<frame>. Scrubbing replaces the entry (settled); picking a clip adds one. */
export function useDiveState(doc: ClipsDoc) {
  const [state, setState] = useState<DiveState>(() => parseLocation(window.location.search, doc));
  const clip: Clip = doc.clips.find((c) => c.clip === state.clip) ?? doc.clips[0];
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const latest = useRef(state);
  latest.current = state;

  const flush = useCallback(() => {
    if (timer.current === undefined) return;
    clearTimeout(timer.current);
    timer.current = undefined;
    const search = serialise(latest.current);
    if (window.location.search !== search) window.history.replaceState(null, "", search);
  }, []);

  useEffect(() => {
    const onPop = () => { clearTimeout(timer.current); timer.current = undefined; setState(parseLocation(window.location.search, doc)); };
    window.addEventListener("popstate", onPop);
    return () => { window.removeEventListener("popstate", onPop); flush(); };
  }, [doc, flush]);

  const setFrame = useCallback((f: number) => {
    setState((s) => {
      const c = doc.clips.find((x) => x.clip === s.clip) ?? doc.clips[0];
      const frame = clampFrame(f, c.n_frames);
      return frame === s.frame ? s : { clip: s.clip, frame };
    });
    clearTimeout(timer.current);
    timer.current = setTimeout(flush, URL_SETTLE_MS);
  }, [doc, flush]);

  const setClip = useCallback((id: string) => {
    const c = doc.clips.find((x) => x.clip === id);
    if (!c) return;
    clearTimeout(timer.current);
    timer.current = undefined;
    const next = { clip: c.clip, frame: findingFrame(c) };
    window.history.pushState(null, "", serialise(next));
    setState(next);
  }, [doc]);

  return { clip, frame: state.frame, setFrame, setClip };
}
