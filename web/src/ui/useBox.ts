import { useLayoutEffect, useRef, useState } from "react";

/** The element's content width, kept current with a ResizeObserver (the StillDrawn Explorer's useBox). `fallback` is used until
 *  it has measured, and where there is no ResizeObserver at all (jsdom), so a test still draws a curve. */
export function useWidth<T extends HTMLElement>(fallback = 640) {
  const ref = useRef<T>(null);
  const [w, setW] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const set = (x: number) => setW((old) => (x > 0 && Math.round(x) !== old ? Math.round(x) : old));
    set(el.getBoundingClientRect().width);
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => set(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}
