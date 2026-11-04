import type { Clip } from "../data/types";
import { conditionName, engineName, PROMPT_WORDS } from "../lib/names";
import { Segmented } from "../ui/Segmented";
import { useMedia } from "../ui/useMedia";
import { lengthsFor, resolve, valuesOf, type Dims } from "./options";

/** Recording, engine and prompt as three segmented controls (three selects on a phone: the recording on its own row, so its
 *  name is never cut; engine and prompt share the next), and 5 s / 10 s where a dive exists. */
export function Picker({ clips, clip, onPick }: { clips: Clip[]; clip: Clip; onPick: (id: string) => void }) {
  const narrow = useMedia("(max-width: 640px)");
  const change = (c: Partial<Dims>) => onPick(resolve(clips, clip, c).clip);
  const rec = valuesOf(clips, "condition").map((v) => ({ value: v, label: conditionName(v) }));
  const eng = valuesOf(clips, "engine").map((v) => ({ value: v, label: engineName(v) }));
  // the prompts are letters; the words are the legend (the chosen one) and a tooltip on each (all three, with the wording the engine was given)
  const wording = (v: string) => clips.find((c) => c.prompt === v)?.prompt_text;
  const pro = valuesOf(clips, "prompt").map((v) => ({ value: v, label: v, title: `${v}: ${PROMPT_WORDS[v] ?? v}${wording(v) ? `. The engine was told: \u201c${wording(v)}\u201d` : ""}` }));
  const promptLabel = `Prompt \u00b7 ${PROMPT_WORDS[clip.prompt] ?? clip.prompt}`;
  const lens = lengthsFor(clips, clip);
  const select = (label: string, value: string, options: { value: string; label: string; title?: string }[], on: (v: string) => void) => (
    <label className="pick-select"><span className="field-label">{label}</span>
      <select className="select" value={value} onChange={(e) => on(e.target.value)}>{options.map((o) => <option key={o.value} value={o.value} title={o.title}>{o.label}</option>)}</select>
    </label>
  );
  return (
    <div className="picker" role="group" aria-label="Choose a clip">
      {narrow ? (
        <>
          {select("Recording", clip.condition, rec, (v) => change({ condition: v }))}
          {select("Engine", clip.engine, eng, (v) => change({ engine: v }))}
          {select(promptLabel, clip.prompt, pro, (v) => change({ prompt: v }))}
        </>
      ) : (
        <>
          <Segmented label="Recording" value={clip.condition} options={rec} onChange={(v) => change({ condition: v })} />
          <Segmented label="Engine" value={clip.engine} options={eng} onChange={(v) => change({ engine: v })} />
          <Segmented label={promptLabel} value={clip.prompt} options={pro} onChange={(v) => change({ prompt: v })} />
        </>
      )}
      {lens.length > 1 && (
        <Segmented label="Length" value={String(clip.seconds)} options={lens.map((s) => ({ value: String(s), label: `${s} s` }))}
          onChange={(v) => change({ seconds: Number(v) })} />
      )}
    </div>
  );
}
