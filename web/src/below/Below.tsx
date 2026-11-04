import { memo } from "react";
import type { Clip } from "../data/types";
import { DOI } from "../shell/TopBar";
import { DATASET, DERIVED_VISUALS, GENERATED, LICENCES, MODELS, NON_COMMERCIAL } from "./credits";
import { notesFor } from "./notes";
import { HOW_TO_READ, STATEMENT, wallTestLimit } from "./text";
import { PlainBand, PlainInvite, PlainNote } from "../plainwords/PlainWords";
import "./below.css";

/** The statement, how to read D and V, the wall test's limit. Static words (data-static): the figures test skips them. */
export const Statement = memo(function Statement({ condition = "" }: { condition?: string }) {
  return (
    <section id="statement" className="panel prose" data-static aria-labelledby="statement-h">
      <h2 id="statement-h">About this measure</h2>
      <PlainNote id="numbers.scale" />
      <p>{STATEMENT[0]}</p>
      <PlainNote id="stereo" />
      {STATEMENT.slice(1).map((p) => <p key={p}>{p}</p>)}
      <dl className="how">
        {HOW_TO_READ.map((r) => <div key={r.term}><dt>{r.term}</dt><dd>{r.text}</dd></div>)}
      </dl>
      <h3>What the wall test can and cannot say</h3>
      <p>{wallTestLimit(condition)}</p>
    </section>
  );
});

/** The current clip's notes and its provenance: the prompt, the seed, the file's origin. Figures come from the clip. */
export const ClipNotes = memo(function ClipNotes({ clip }: { clip: Clip }) {
  return (
    <section className="panel prose" aria-labelledby="notes-h">
      <h2 id="notes-h">Notes on this clip</h2>
      <ul className="notes">{notesFor(clip).map((n) => <li key={n.id} data-note={n.id}>{n.text}</li>)}</ul>
      <h3>Provenance</h3>
      <dl className="prov">
        <div><dt>Prompt</dt><dd>“{clip.prompt_text}”</dd></div>
        <div><dt>Seed</dt><dd className="mono">{clip.seed}</dd></div>
        <div><dt>The bare clip</dt><dd>the engine's own file, byte for byte (<span className="mono">sha256 {clip.provenance.source_sha256}</span>)</dd></div>
        <div><dt>Heat and the rebuilt tank</dt><dd>derived pictures, made here</dd></div>
      </dl>
    </section>
  );
});

/** Zenodo's citation ends in its DOI URL; that URL is the link. */
const citeUrl = DATASET.citation.slice(DATASET.citation.indexOf("https://"));
const citeText = DATASET.citation.slice(0, DATASET.citation.indexOf("https://")).trimEnd();

export const Credits = memo(function Credits() {
  return (
    <section className="panel prose" data-static aria-labelledby="credits-h">
      <h2 id="credits-h">Credits</h2>
      <p>{DATASET.text}</p>
      <p className="citation">{citeText} <a href={`https://doi.org/${DOI}`} rel="noopener">{citeUrl}</a></p>
      <ul className="credits">{MODELS.map((m) => <li key={m.name}><strong>{m.name}</strong>, {m.by}, {m.licence}: {m.used}.</li>)}</ul>
      <p>{DERIVED_VISUALS}</p>
      <p>{GENERATED}</p>
      <p>Licence texts: {LICENCES.map((l, i) => <span key={l.name}>{i > 0 ? ", " : ""}<a href={l.url} rel="noopener">{l.name}</a></span>)}.</p>
      <p className="muted">{NON_COMMERCIAL}</p>
    </section>
  );
});

/** Mount points for the plain-words layer (task 4.4): the invite under the title row, and the three chapter bands (above the stage,
 *  above the evidence row, above the statement). Each slot is empty until the reader asks for the layer (src/plainwords/). */
export const PlainWordsMount = ({ slot }: { slot: "invite" | "chapter-1" | "chapter-2" | "chapter-3" }) => (
  <div data-plain-words={slot}>{slot === "invite" ? <PlainInvite /> : <PlainBand n={Number(slot.slice(-1))} />}</div>
);
