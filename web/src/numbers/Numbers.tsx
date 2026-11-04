import type { Clip, ClipsDoc } from "../data/types";
import { agreementText, pathAgreement } from "../lib/agreement";
import { cellText, fmtD, fmtSeconds, fmtSu, fmtV, reasonText, UNVERIFIABLE } from "../lib/format";
import { conditionName } from "../lib/names";
import { D_REF, D_RUN, D_THRESHOLD, dAt, forwardAt, vAt } from "../lib/series";
import { PlainNote } from "../plainwords/PlainWords";
import "./numbers.css";

/** A distance in su: the figure, then the unit as a grey suffix (named in full once, in the statement). */
export const Su = ({ v }: { v: number }) => <span className="num">{fmtSu(v)}<abbr className="unit" title="uncorrected stereo units">&#8239;su</abbr></span>;

/** The start of a sentence: a capital after a full stop. */
const sentence = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

/** The numbers, as one divided container: D now (the lead), V now, distance against the far end, the departure, path agreement. */
export function Numbers({ doc, clip, frame }: { doc: ClipsDoc; clip: Clip; frame: number }) {
  const rec = doc.recordings[clip.recording_key];
  const d = dAt(clip, frame), v = vAt(clip, frame), fwd = forwardAt(clip, frame);
  const gold = d.kind === "value" && d.value > D_THRESHOLD;
  const a = pathAgreement(clip);
  const dep = clip.first_D3;
  return (
    <dl className="numbers" aria-label="The numbers at the cursor">
      <div className="n-lead">
        <dt>D now</dt>
        <dd className={`lead num${gold ? " is-gold" : ""}`} data-gold={gold || undefined}>{cellText(d, fmtD)}</dd>
        <dd className="n-note">
          {D_REF} = no worse than mono depth on the real tank. The floor, mono depth's own error on the real frames of {conditionName(clip.condition)}, is {rec.floor.toFixed(3)}.
          A faithful dream scores {rec.null_dream_D.median.toFixed(2)} here.
          {d.kind === "unverifiable" && <> {sentence(reasonText(clip))}.</>}
        </dd>
      </div>
      <div>
        <dt>V now</dt>
        <dd className="num">{cellText(v, fmtV)}</dd>
        <dd className="n-note">{v.kind === "unverifiable" ? reasonText(clip) : "the share of the frame the rebuilt tank covers, leaving out a tracked moving object"}</dd>
        <PlainNote id="numbers.V" inList />
      </div>
      <div>
        <dt>Forward distance</dt>
        <dd>{fwd.kind === "value" ? <Su v={fwd.value} /> : <span>{UNVERIFIABLE}</span>}</dd>
        <dd className="n-note">along the first camera's view. {clip.far_end_valid && clip.far_end !== null ? <>The far end as measured is at <Su v={clip.far_end} />.</> : "The far end was not measured."} Straight-line travel to the last trusted frame: <Su v={clip.travel} />.</dd>
      </div>
      <div className="n-dep">
        <dt>Departure</dt>
        <dd className="num">{dep === null ? "none" : `f${dep} · ${fmtSeconds(dep, clip.fps, 2)} s`}</dd>
        <dd className="n-note">{`D above ${D_THRESHOLD} for ${D_RUN} frames running (half a second)`}</dd>
      </div>
      <div className="n-agree">
        <dt>Path agreement</dt>
        <dd>{a ? <><Su v={a.su} /></> : <span>{UNVERIFIABLE}</span>}</dd>
        <dd className="n-note">
          {a ? <>between two path estimates at their widest (f{a.frame}), {agreementText(a).share}. The second estimate almost always does worse than assuming a still camera, so a wide gap mostly measures that estimate failing, not doubt about the main path.</>
            : "no second path past a cap or a loss"}
        </dd>
      </div>
    </dl>
  );
}
