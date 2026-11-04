import { Fragment, memo } from "react";
import type { Clip } from "../data/types";
import type { FindingKind } from "../lib/finding";
import { fmtV } from "../lib/format";
import { engineName } from "../lib/names";
import { D_THRESHOLD } from "../lib/series";
import { steadyV, tally, tallyWords } from "../lib/tally";
import "./band.css";

/** The study's answer in one line (hub call 92). Not a heading: the h1 stays the clip. No figure in it. */
export const ANSWER = "A dream can be checked against the real tank frame by frame, until it leaves what was measured.";

/**
 * The two surprises (THESIS.md), one line each, in the page's technical voice. The threshold comes from the code and V from the data.
 * - The first is read from the heat, not from clips.json: in all five clips past 3 the new pale heat is the blue "reads farther" ramp
 *   (LOG.md, "Findings band"); the warm heat that also grows on the Wan clips sits on outlined actors, which D leaves out.
 * - The second is computed (lib/tally steadyV) and is left out if the data stops bearing it out. It names the engine because the Wan
 *   departures do let V fall (to 0.54), where tracked actors are taken out of it.
 */
export function surprises(clips: Clip[]): { lead: string; rest: string }[] {
  const out = [{ lead: "Dreams open the tank up:", rest: `in every clip past ${D_THRESHOLD}, the invented space reads farther than the real tank.` }];
  const s = steadyV(clips);
  if (s) out.push({ lead: "Only D sees a dream leave:", rest: `the ${engineName(s.engine)} clips past ${D_THRESHOLD} keep V at ${fmtV(s.v)}; the rebuilt tank still covers the frame.` });
  return out;
}

/** Between the title row and the stage: the answer, the tally (each count brings its clips forward in the clip table), the surprises.
 *  It takes none of the departure colour (that is D above 3 only, held by the colour test) and has no entrance motion. */
export const Band = memo(function Band({ clips, onShow }: { clips: Clip[]; onShow: (kind: FindingKind) => void }) {
  const groups = tally(clips);
  return (
    <section className="band" aria-label="What the clips show">
      <div className="band-top">
        <p className="band-answer">{ANSWER}</p>
        <div className="tally" role="group" aria-label={`The ${clips.length} clips, by their finding line`}>
          {groups.map((g, i) => {
            const text = `${g.n} ${tallyWords(g.kind, g.n)}`;
            return (
              <Fragment key={g.kind}>
                {i > 0 && <span className="tally-sep" aria-hidden="true"> · </span>}
                <button type="button" className="tally-btn" data-kind={g.kind} aria-label={`${text}: show them in the clip table`} onClick={() => onShow(g.kind)}>
                  <span className="tally-n">{g.n}</span> {tallyWords(g.kind, g.n)}
                </button>
              </Fragment>
            );
          })}
        </div>
      </div>
      <ul className="surprises">
        {surprises(clips).map((s) => <li key={s.lead}><strong>{s.lead}</strong> {s.rest}</li>)}
      </ul>
    </section>
  );
});
