import { Component, lazy, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Clip, ClipsDoc } from "../data/types";
import { RELIEF_COLOUR, RELIEF_NO_WEBGL, RELIEF_NOTE, RELIEF_OUTLINE, RELIEF_STILL_NOTE } from "../below/text";
import { reliefFrame, unplacedText } from "./frameData";
import { ReliefStill } from "./ReliefStill";
import { useReliefData } from "./useRelief";
import "./relief.css";

const ReliefCanvas = lazy(() => import("./ReliefCanvas"));          // three stays out of the first load

/** Can this browser start WebGL? Asked once per page (every probe makes a context, and browsers cap them), and the probe is released. */
export function canWebgl(): boolean {
  try {
    const c = document.createElement("canvas");
    const gl = (c.getContext("webgl2") || c.getContext("webgl")) as WebGLRenderingContext | null;
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
    return !!gl;
  } catch { return false; }
}

/** The accessible name of the relief, still or canvas: what the colour is first, then what is drawn. */
export const reliefLabel = (frame: number, what: string, unplaced: string | null = null): string =>
  `${RELIEF_COLOUR} The gap between the dream and the tank at frame ${frame}, as ${what}.${unplaced ? ` ${unplaced}` : ""} ${RELIEF_OUTLINE}`;

const matches = (q: string) => typeof matchMedia === "function" && matchMedia(q).matches;

class Boundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

/**
 * The relief. Live on a desktop; a still (the gap map) on a phone until tapped, with reduced motion, or when WebGL will not start.
 * The atlases load only once the panel is near the screen. The canvas takes pan-y touches, so it never traps the page's scroll.
 */
export function ReliefPanel({ doc, clip, frame, base, webgl }: { doc: ClipsDoc; clip: Clip; frame: number; base: string; webgl?: boolean }) {
  const [detected] = useState(canWebgl);                       // once: not on every frame
  const gl = webgl ?? detected;
  const box = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState(typeof IntersectionObserver === "undefined");
  useEffect(() => {
    const el = box.current;
    if (!el || near || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setNear(true), { rootMargin: "300px" });
    io.observe(el);
    return () => io.disconnect();
  }, [near]);
  const [armed, setArmed] = useState(false);
  useEffect(() => setArmed(false), [clip.clip]);
  const reduced = matches("(prefers-reduced-motion: reduce)");
  const phone = matches("(max-width: 760px)");
  const live = gl && (armed || (!reduced && !phone));
  const data = useReliefData(clip, base, near);
  const f = useMemo(() => (data && data !== "error" && data.clip === clip.clip ? reliefFrame(clip, doc.heat, data, frame) : null), [data, clip, doc.heat, frame]);
  const unplaced = f && !f.dream ? unplacedText(clip, frame) : null;
  const still = <ReliefStill gap={f?.gap ?? null} heat={doc.heat} label={reliefLabel(frame, "a still", unplaced)} />;
  return (
    <div className="relief" ref={box}>
      <div className="relief-frame" data-live={live || undefined}>
        {data === "error" ? <p className="muted" role="alert">The depth atlas could not be loaded.</p>
          : !f ? <p className="muted" role="status">Loading the surfaces…</p>
          : live ? (
            <Boundary fallback={still}>
              <Suspense fallback={still}><ReliefCanvas frame={f} instant={reduced} label={reliefLabel(frame, "the surfaces, which can be turned by dragging", unplaced)} /></Suspense>
            </Boundary>
          ) : still}
      </div>
      {!live && gl && f && <button type="button" className="btn" onClick={() => setArmed(true)}>Orbit the surfaces</button>}
      {/* with no atlas there is no still to describe: say what is missing and that nothing else is (break-ui, task 4.6) */}
      <p className="small muted">{data === "error" ? "Without it the surfaces cannot be drawn. Everything else on the page still works." : <>{unplaced && `${unplaced} `}{live ? RELIEF_NOTE : gl ? `${RELIEF_STILL_NOTE} ${RELIEF_NOTE}` : `${RELIEF_NO_WEBGL} ${RELIEF_NOTE}`}</>}</p>
    </div>
  );
}
