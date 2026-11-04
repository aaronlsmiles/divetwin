// The plain-words layer: the invite, the three chapter bands down the one page, the notes pinned beside the parts, and the top bar's
// switch. Nothing renders unless the reader asks; with the layer off the page is exactly as it was. Blue pencil sits only on its own
// wash (the bands, the invite, the notes), never over the media (call 86).
import { useEffect, type MouseEvent } from "react";
import { usePlainWords } from "./state";
import { CHAPTERS, noteFor, UI, type NoteId } from "./words";
import "./plainwords.css";

/** The blue-pencil mark that signs the voice (the same path as studionephele.com's and the explorer's). */
export function Pencil() {
  return (
    <svg className="pw-mark" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d="M2.5 13.5 3.4 10 11 2.4a1.4 1.4 0 0 1 2 0l.6.6a1.4 1.4 0 0 1 0 2L6 12.6ZM9.6 3.8l2.6 2.6M3.4 10l2.6 2.6"
        fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

const reduced = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Bring a band to the top of the screen (under the bar) and put focus in it, so a reader's place and focus move together. */
export function goToBand(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView?.({ behavior: reduced() ? "auto" : "smooth", block: "start" });
  el.focus({ preventScroll: true });
}

/** A band asked for before it exists (the switch pressed while the clips are still loading): the band takes focus when it mounts. */
let pending: string | null = null;

/** Turning the layer on moves focus into the first band: now, or as soon as the band is on the page. */
function openAt(id: string) {
  requestAnimationFrame(() => {
    if (document.getElementById(id)) { pending = null; goToBand(id); } else pending = id;
  });
}

/** Where focus goes when the layer is put away: the switch that brings it back (inside Menu on phones). */
function focusSwitch() {
  pending = null;
  requestAnimationFrame(() => {
    const sw = document.querySelector<HTMLElement>(".plain-btn");
    (sw && sw.offsetParent ? sw : document.querySelector<HTMLElement>(".bar-menu"))?.focus({ preventScroll: true });
  });
}

/** The top bar's switch: "Plain words", pressed while the layer is on. */
export function PlainSwitch({ after }: { after?: () => void }) {
  const { mode, set } = usePlainWords();
  const on = mode === "on";
  return (
    <button type="button" className="theme-btn plain-btn" aria-pressed={on}
      onClick={() => { set(on ? "off" : "on"); after?.(); if (on) pending = null; else openAt(CHAPTERS[0].id); }}>
      <Pencil />{UI.toggle}
    </button>
  );
}

/** The invite, one slim line under the finding, until the reader chooses. */
export function PlainInvite() {
  const { mode, set, later } = usePlainWords();
  if (mode !== "unset") return null;
  return (
    <aside className="pw-invite" aria-label={UI.label}>
      <Pencil />
      <span className="pw-lead">{UI.invite}</span>
      <button type="button" className="pw-btn" onClick={() => { set("on"); openAt(CHAPTERS[0].id); }}>
        {UI.follow} <span aria-hidden="true">→</span>
      </button>
      <button type="button" className="pw-quiet" onClick={() => { later(); focusSwitch(); }}>{UI.notNow}</button>
    </aside>
  );
}

/** One chapter's band (n counts from 1). "Next" scrolls to the next band and focuses it; the last leads back to the first. */
export function PlainBand({ n }: { n: number }) {
  const { mode, set } = usePlainWords();
  const i = n - 1, chapter = CHAPTERS[i];
  useEffect(() => {
    if (mode === "on" && pending === chapter.id) { pending = null; goToBand(chapter.id); }
  }, [mode, chapter.id]);
  if (mode !== "on") return null;
  const next = CHAPTERS[i + 1];
  const go = (id: string) => (e: MouseEvent) => { e.preventDefault(); goToBand(id); };
  return (
    <aside className="pw-band" id={chapter.id} aria-label={`${UI.label}, chapter ${n} of ${CHAPTERS.length}`} tabIndex={-1} data-chapter={n}>
      <div className="pw-head">
        <h2 className="pw-title"><Pencil />{chapter.title}</h2>
        <p className="pw-pos">{UI.label}, chapter {n} of {CHAPTERS.length}</p>
      </div>
      <div className="pw-text">
        {chapter.band.map((t) => <p key={t}>{t}</p>)}
      </div>
      <p className="pw-foot">
        {next
          ? <a className="pw-next" href={`#${next.id}`} onClick={go(next.id)}>{UI.next}: {next.title} <span aria-hidden="true">→</span></a>
          : <a className="pw-next" href={`#${CHAPTERS[0].id}`} onClick={go(CHAPTERS[0].id)}>{UI.again} <span aria-hidden="true">→</span></a>}
        <button type="button" className="pw-quiet" onClick={() => { set("off"); focusSwitch(); }}>{UI.hide}</button>
      </p>
      {/* three bands hold three maps, so each landmark has its own name (axe landmark-unique) */}
      <nav className="pw-map" aria-label={`${UI.label}: ${UI.story.toLowerCase()}, in chapter ${n}`}>
        <ol>
          {CHAPTERS.map((c, k) => (
            <li key={c.id}>
              <a href={`#${c.id}`} onClick={go(c.id)} aria-current={k === i ? "step" : undefined}>
                <span className="pw-n">{k + 1}</span>{c.title}{k === i && <Ring />}
              </a>
            </li>
          ))}
        </ol>
      </nav>
    </aside>
  );
}

/** The explorer's grease-pencil loop, drawn in blue pencil around the chapter you're on. */
function Ring() {
  return (
    <svg className="pw-ring" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true" focusable="false">
      <path d="M58 3.2C30 1.6 4.5 6 3.2 15.4 2 25.6 26 29.6 52 29 80 28.4 97.4 23.4 96.8 14.6 96.2 5.8 74 1.8 41 4.6"
        fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** A note before (or beside) the part of the page it explains; nothing at all while the layer is off. `condition` picks Air's
 *  wording where it differs; `inList` wraps it in a <dd> so it can sit inside the numbers' description list. */
export function PlainNote({ id, condition = "", inList = false }: { id: NoteId; condition?: string; inList?: boolean }) {
  const { mode } = usePlainWords();
  if (mode !== "on") return null;
  const note = (
    <div className="pw-note" role="note" data-note={id}>
      <Pencil />
      <div className="pw-text">
        <span className="visually-hidden">{UI.label}: </span>
        {noteFor(id, condition).map((t) => <p key={t}>{t}</p>)}
      </div>
    </div>
  );
  return inList ? <dd className="pw-dd">{note}</dd> : note;
}
