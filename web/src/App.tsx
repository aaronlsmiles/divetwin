import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { TopBar } from "./shell/TopBar";
import { mediaBase, mediaUrl } from "./data/media";
import { useClipsDoc } from "./data/useClipsDoc";
import type { ClipsDoc } from "./data/types";
import { clipTitle, finding, type FindingKind } from "./lib/finding";
import { tally, tallyWords } from "./lib/tally";
import { Band } from "./band/Band";
import { useDiveState } from "./state/urlState";
import { Stage } from "./stage/Stage";
import { Scrubber, SCRUBBER_ID } from "./scrubber/Scrubber";
import { PlanView, usePlanData } from "./plan/PlanView";
import { Numbers } from "./numbers/Numbers";
import { ReliefPanel } from "./relief/ReliefPanel";
import { Picker } from "./picker/Picker";
import { ClipTable } from "./table/ClipTable";
import { ClipNotes, Credits, PlainWordsMount, Statement } from "./below/Below";
import { PlainWordsProvider } from "./plainwords/state";
import { PlainNote } from "./plainwords/PlainWords";
import { PHONE, useMedia } from "./ui/useMedia";

function Dive({ doc, base }: { doc: ClipsDoc; base: string }) {
  const { clip, frame, setFrame, setClip } = useDiveState(doc);
  const [playing, setPlaying] = useState(false);
  useEffect(() => setPlaying(false), [clip.clip]);
  useEffect(() => { document.title = `${clipTitle(clip)} · Dive Twin`; }, [clip]);
  const plan = usePlanData(doc, clip, base);
  const rec = doc.recordings[clip.recording_key];
  // the evidence row: the plan view, the relief and the numbers side by side; on a phone the numbers lead (docs/DESIGN.md). The DOM is
  // reordered rather than CSS `order`, so the reading and Tab order follow what the reader sees.
  const phone = useMedia(PHONE);
  const planPanel = (
    <section className="panel panel-plan" key="plan">
      <h2>Where the camera went</h2>
      <PlainNote id="plan" condition={clip.condition} />
      {plan === null && <div className="ph">Loading the plan…</div>}
      {plan === "error" && <p className="muted" role="alert">The path could not be loaded.</p>}
      {plan && plan !== "error" && plan.clip === clip.clip && <PlanView clip={clip} plan={plan.plan} path={plan.path} frame={frame} />}
    </section>
  );
  const relief = <section className="panel panel-relief" key="relief"><h2>The two tanks as surfaces</h2><PlainNote id="relief" /><ReliefPanel doc={doc} clip={clip} frame={frame} base={base} /></section>;
  const numbers = <section className="panel panel-numbers" key="numbers"><h2>The numbers</h2><Numbers doc={doc} clip={clip} frame={frame} /></section>;
  const reduce = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  // choosing a row in the table loads the stage, so bring the stage into view
  const pickFromTable = useCallback((id: string) => {
    setClip(id);
    document.getElementById("main")?.scrollIntoView?.({ behavior: reduce() ? "auto" : "smooth" });
  }, [setClip]);
  // a count in the findings band brings its clips forward: the table shows only them, and the line that says so takes focus and scrolls
  // into view (call 92). The stage keeps its clip; choosing a row loads one, and "Show all" brings every clip back.
  const [group, setGroup] = useState<FindingKind | null>(null);
  // memoised: the frame changes 24 times a second while playing, and the table (memo) must not re-render for it
  const shown = useMemo(() => (group === null ? null : tally(doc.clips).find((g) => g.kind === group) ?? null), [group, doc.clips]);
  const only = useMemo(() => (shown === null ? null : new Set(shown.clips.map((c) => c.clip))), [shown]);
  const [asked, setAsked] = useState(0);
  const filterLine = useRef<HTMLParagraphElement>(null);
  const showGroup = useCallback((kind: FindingKind) => { setGroup(kind); setAsked((n) => n + 1); }, []);
  useEffect(() => {
    if (asked === 0) return;
    // the table's own section comes to the top, under the sticky bar (its scroll-margin), so its heading and the line both read
    const line = filterLine.current;
    line?.closest("section")?.scrollIntoView?.({ behavior: reduce() ? "auto" : "smooth", block: "start" });
    line?.focus({ preventScroll: true });
  }, [asked]);
  return (
    <>
      <div className="title-row">
        <div className="title-text">
          {/* each part of the breadcrumb keeps together, so a phone breaks the title at a " · ", never inside "Gen-4.5" */}
          {/* a separator ends the crumb before it (the text still reads "A · B · C"), so a wrapped title ends a line on a "·" and never starts one with it */}
          <h1>{clipTitle(clip).split(" · ").map((part, i, all) => <Fragment key={i}>{i > 0 && " "}<span className="crumb">{part}{i < all.length - 1 && " ·"}</span></Fragment>)}</h1>
          <p className="finding">{finding(clip)}</p>
          {/* the invite sits under the finding, in the title's own column: a first visit keeps the evidence row's headers on the first screen */}
          <PlainWordsMount slot="invite" />
        </div>
        <Picker clips={doc.clips} clip={clip} onPick={setClip} />
      </div>
      <Band clips={doc.clips} onShow={showGroup} />
      <PlainWordsMount slot="chapter-1" />

      <Stage doc={doc} clip={clip} frame={frame} base={base} playing={playing} setFrame={setFrame} setPlaying={setPlaying}>
        <Scrubber clip={clip} heat={doc.heat} frame={frame} setFrame={setFrame} playing={playing}
          onTogglePlay={() => setPlaying((p) => !p)} startUrl={mediaUrl(rec.start, base)} />
        {/* the scrubber's note follows it, so the panes and the line under them stay together with the layer on */}
        <PlainNote id="scrubber" />
      </Stage>
      <PlainWordsMount slot="chapter-2" />

      <div className="evidence">
        {phone ? <>{numbers}{planPanel}{relief}</> : <>{planPanel}{relief}{numbers}</>}
      </div>

      <div className="below">
        <PlainWordsMount slot="chapter-3" />
        <Statement condition={clip.condition} />
        <ClipNotes clip={clip} />
        <section className="panel panel-table" aria-labelledby="table-h">
          <h2 id="table-h">All {doc.clips.length} clips</h2>
          {shown && (
            <p className="table-filter" ref={filterLine} tabIndex={-1}>
              <span>Showing the {shown.n} {shown.n === 1 ? "clip" : "clips"} that {tallyWords(shown.kind, shown.n)}.</span>{" "}
              <button type="button" className="btn-text" onClick={() => setGroup(null)}>Show all {doc.clips.length}</button>
            </p>
          )}
          <ClipTable clips={doc.clips} current={clip.clip} onPick={pickFromTable} only={only} />
        </section>
        <Credits />
      </div>
    </>
  );
}

export function App() {
  const base = mediaBase();
  const [attempt, setAttempt] = useState(0);
  const state = useClipsDoc(base, attempt);
  return (
    <PlainWordsProvider>
      <a className="skip" href="#main">Skip to the dive</a>
      {/* Tab follows the page as it reads (the picker before the stage), so the most frequent job, scrubbing, has its own way in: the second stop */}
      <a className="skip" href={`#${SCRUBBER_ID}`} onClick={(e) => { const el = document.getElementById(SCRUBBER_ID); if (el) { e.preventDefault(); el.focus(); el.scrollIntoView?.({ block: "center" }); } }}>Skip to the scrubber</a>
      <TopBar />
      <main id="main" className="page">
        {state.status === "loading" && <p role="status" className="muted">Loading the clips…</p>}
        {state.status === "error" && (
          <div className="state-error" role="alert">
            <h1>The dive could not be loaded</h1>
            <p className="muted">{state.message}</p>
            <button type="button" className="btn" onClick={() => setAttempt((a) => a + 1)}>Try again</button>
          </div>
        )}
        {state.status === "ready" && <Dive doc={state.doc} base={base} />}
      </main>
    </PlainWordsProvider>
  );
}
