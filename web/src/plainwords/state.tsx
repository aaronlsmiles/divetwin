import { createContext, use, useEffect, useState, type ReactNode } from "react";

/** unset: the invite shows; on: bands and notes; off: only the top-bar switch. */
export type PlainMode = "unset" | "on" | "off";
export const KEY = "dt-plain";
/** "Not now" puts the invite away for this visit only; the next visit asks again. */
export const LATER = "dt-plain-later";

function store(m: "on" | "off") {
  try { localStorage.setItem(KEY, m); } catch { /* storage may be unavailable */ }
}

/** ?plain=1 or ?plain=0 wins (a link sent to someone), then the stored choice, then "Not now" for this visit. */
export function initialMode(search = location.search): PlainMode {
  const q = new URLSearchParams(search).get("plain");
  const asked = q === "1" ? "on" : q === "0" ? "off" : null;
  if (asked) { store(asked); return asked; }
  try {
    const v = localStorage.getItem(KEY);
    if (v === "on" || v === "off") return v;
    if (sessionStorage.getItem(LATER)) return "off";
  } catch { /* storage may be unavailable: the choice lasts for this visit */ }
  return "unset";
}

/** A reader's own click settles it: drop ?plain= from the address (and only that), so a reload keeps what they chose. */
function dropParam() {
  try {
    const u = new URL(location.href);
    if (!u.searchParams.has("plain")) return;
    u.searchParams.delete("plain");
    history.replaceState(history.state, "", u.pathname + u.search + u.hash);
  } catch { /* leave the address alone */ }
}

/** The studio's sites share no storage (and public pages set no cookies), so the choice travels on links: with the layer on, every
 *  link into another studio site opens its plain telling (?plain=1); with it off, those links are left plain, and the other site
 *  keeps whatever its reader chose there (the hub's docs/plain-words.md, "One layer across the studio's sites"). */
export const STUDIO_DOMAIN = "studionephele.com";
export function isStudioSite(host: string, here = location.host): boolean {
  return host !== here && (host === STUDIO_DOMAIN || host.endsWith(`.${STUDIO_DOMAIN}`));
}
export function carry(on: boolean, root: ParentNode = document) {
  for (const a of root.querySelectorAll<HTMLAnchorElement>("a[href]")) {
    let u: URL;
    try { u = new URL(a.href); } catch { continue; }
    if (!isStudioSite(u.host)) continue;
    const had = u.searchParams.get("plain");
    if (on && had !== "1") u.searchParams.set("plain", "1");
    else if (!on && had !== null) u.searchParams.delete("plain");
    else continue;
    a.href = u.href;
  }
}

/** Keeps carry() true as the page renders new links (a clip change re-renders parts of the page). */
function useCarry(on: boolean) {
  useEffect(() => {
    carry(on);
    if (typeof MutationObserver === "undefined") return;
    const mo = new MutationObserver(() => carry(on));
    mo.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["href"] });
    return () => mo.disconnect();
  }, [on]);
}

type Plain = { mode: PlainMode; set: (m: "on" | "off") => void; later: () => void };
/** Outside the provider the layer is simply not there (a component rendered on its own shows nothing of it). */
const Ctx = createContext<Plain>({ mode: "off", set: () => {}, later: () => {} });

export function PlainWordsProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<PlainMode>(() => initialMode());
  useCarry(mode === "on");
  const set = (m: "on" | "off") => { setMode(m); store(m); dropParam(); };
  const later = () => {
    setMode("off");
    try { sessionStorage.setItem(LATER, "1"); } catch { /* the invite then stays away until a reload */ }
    dropParam();
  };
  return <Ctx value={{ mode, set, later }}>{children}</Ctx>;
}

export const usePlainWords = () => use(Ctx);
