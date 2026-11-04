import { useEffect, useRef, type RefObject } from "react";
import { timeFor } from "../lib/frames";

/** requestVideoFrameCallback is in the DOM types but missing from older browsers: it is checked at run time. */
const hasVfc = (v: HTMLVideoElement): boolean => typeof v.requestVideoFrameCallback === "function";

/** The frame a presented picture is: its media time is n / fps (we seek to the middle of a frame and play from there). */
export const frameFromMediaTime = (t: number, fps: number, n: number): number => Math.min(n - 1, Math.max(0, Math.round(t * fps)));

const go = (v: HTMLVideoElement, t: number) => { if (Math.abs(v.currentTime - t) > 1e-4) v.currentTime = t; };

/**
 * Scrubbing: seek every video to the middle of frame f, all three together (the hidden dream view too, so a switch lands on the same
 * frame). A video without metadata yet is sent to the latest frame when it arrives, not the one it was first asked for.
 * `enabled` is false while playing: native playback owns the clock then, and a seek per frame would stall every pane.
 */
export function useSeek(refs: RefObject<HTMLVideoElement | null>[], frame: number, fps: number, clipKey: string, enabled = true) {
  const target = useRef(0);
  target.current = timeFor(frame, fps);
  useEffect(() => {
    if (!enabled) return;
    const cleanups: (() => void)[] = [];
    for (const v of refs.map((r) => r.current).filter((x): x is HTMLVideoElement => x !== null)) {
      const seek = () => go(v, target.current);
      if (v.readyState >= 1) seek();
      else {
        v.addEventListener("loadedmetadata", seek, { once: true });
        cleanups.push(() => v.removeEventListener("loadedmetadata", seek));
      }
    }
    return () => cleanups.forEach((c) => c());
    // the refs are stable objects; the seek reruns when the frame, the clip, the rate or the mode changes
  }, [frame, fps, clipKey, enabled]);
}

/**
 * Play, natively: the real pane and the visible dream view play() on their own clocks, and the cursor follows the real pane's
 * presented frames (requestVideoFrameCallback's mediaTime; a requestAnimationFrame read of currentTime where that is missing).
 * A dream view that drifts more than one frame from the real pane is put back with a seek. The hidden view is never played; it is
 * seeked on pause (useSeek) and when the view is switched. At the last frame, or when the real pane ends, play stops.
 * Seeking per frame is for scrubbing only (useSeek): doing it at 24 Hz on three videos starves the decoder.
 */
export function useNativePlay({ real, dreams, view, clipKey, frame, n, fps, playing, setFrame, setPlaying }: {
  real: RefObject<HTMLVideoElement | null>; dreams: Record<"heat" | "gen", RefObject<HTMLVideoElement | null>>; view: "heat" | "gen";
  clipKey: string; frame: number; n: number; fps: number; playing: boolean; setFrame: (f: number) => void; setPlaying: (p: boolean) => void;
}) {
  const latest = useRef({ frame, view, playing, setFrame, setPlaying });
  latest.current = { frame, view, playing, setFrame, setPlaying };

  useEffect(() => {
    const R = real.current;
    if (!playing || !R) return;
    const visible = () => dreams[latest.current.view].current;
    const stop = () => latest.current.setPlaying(false);
    const start = latest.current.frame >= n - 1 ? 0 : latest.current.frame;
    if (start !== latest.current.frame) latest.current.setFrame(start);
    R.currentTime = timeFor(start, fps);
    const D0 = visible();
    if (D0) D0.currentTime = R.currentTime;
    Promise.resolve(R.play()).catch(stop);                    // play() returns a promise in browsers; Promise.resolve also tolerates a stub that returns nothing
    if (D0) Promise.resolve(D0.play()).catch(() => undefined);

    let live = true, handle = 0, raf = 0;
    const onFrame = (t: number) => {
      if (!latest.current.playing) return;                    // a picture that arrives after Play was ended (a scrub) must not move the cursor
      const f = frameFromMediaTime(t, fps, n);
      latest.current.setFrame(f);
      const D = visible();
      if (D && Math.abs(D.currentTime - R.currentTime) > 1 / fps) D.currentTime = R.currentTime;     // drift over a frame: seek back
      if (f >= n - 1) stop();
    };
    const tick: VideoFrameRequestCallback = (_now, meta) => { if (!live) return; onFrame(meta.mediaTime); handle = R.requestVideoFrameCallback(tick); };
    const loop = () => { if (!live) return; onFrame(R.currentTime); raf = requestAnimationFrame(loop); };
    // Watch for presented pictures only once the seek to the start has landed: until then the pane can still present the picture it was
    // left on (Play from the last frame would read frame 120 and stop at once).
    const begin = () => { if (!live) return; if (hasVfc(R)) handle = R.requestVideoFrameCallback(tick); else raf = requestAnimationFrame(loop); };
    if (R.seeking) R.addEventListener("seeked", begin, { once: true }); else begin();
    const onEnded = () => { latest.current.setFrame(n - 1); stop(); };
    R.addEventListener("ended", onEnded);

    return () => {
      live = false;
      if (handle) R.cancelVideoFrameCallback?.(handle);
      if (raf) cancelAnimationFrame(raf);
      R.removeEventListener("ended", onEnded);
      R.removeEventListener("seeked", begin);
      R.pause(); dreams.heat.current?.pause(); dreams.gen.current?.pause();
    };
    // the clock restarts only when play starts or stops, or the clip changes
  }, [playing, clipKey, fps, n]);

  // a switch of the dream view while playing: the view that comes up plays from the real pane's time, the one that goes stops
  const prev = useRef(view);
  useEffect(() => {
    const changed = prev.current !== view;
    prev.current = view;
    if (!playing || !changed) return;
    const R = real.current, D = dreams[view].current, H = dreams[view === "heat" ? "gen" : "heat"].current;
    H?.pause();
    if (R && D) { D.currentTime = R.currentTime; Promise.resolve(D.play()).catch(() => undefined); }
  }, [view, playing]);
}
