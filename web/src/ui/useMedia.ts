import { useEffect, useState } from "react";

/** Whether a media query matches, kept current. False where there is no matchMedia (a test can stub it). */
export function useMedia(q: string): boolean {
  const [m, setM] = useState(() => typeof matchMedia === "function" && matchMedia(q).matches);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia(q), on = () => setM(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [q]);
  return m;
}

/** The phone layout's breakpoint, shared by the CSS (max-width: 760px) and the evidence row's reading order. */
export const PHONE = "(max-width: 760px)";
