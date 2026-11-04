import { useId, useRef, useState } from "react";
import type { Clip, ClipsDoc } from "../data/types";
import { mediaUrl } from "../data/media";
import { Segmented } from "../ui/Segmented";
import { FloorThumb } from "./FloorThumb";
import { HeatMarks, HeatRamps } from "./HeatKey";
import { useNativePlay, useSeek } from "./sync";
import { rgbCss } from "../lib/palette";
import { clipTitle } from "../lib/finding";
import { isUnverifiable } from "../lib/series";
import { reasonText } from "../lib/format";
import { PlainNote } from "../plainwords/PlainWords";
import "./stage.css";

export type DreamView = "heat" | "bare";

/** The real pane's key line. Past a cap or a loss the tank is still drawn, but the dream can no longer be checked against it. */
export const realCaption = (clip: Clip, frame: number): string =>
  `grey: no real camera looked here${isUnverifiable(clip, frame) ? ", or past where the dream can be checked" : ""}`;

/**
 * The darkroom: the real tank rebuilt from stereo beside the dream, both on the same frame. The dream is a switch between heat.mp4
 * and gen.mp4; all three videos stay mounted (the unused one `hidden`) so a switch never lands on a different frame.
 * Scrubbing seeks all three to the middle of the frame; Play is native (useNativePlay). `children` is the scrubber.
 *
 * Reading order (design pass, 4 Nov): the plain-words notes for both panes, the two panes, the scrubber straight under them (the
 * most frequent job, and the D curve reads against the frames above it), then one key strip for the whole stage: the real
 * pane's grey, the heat's marks and ramps, and the map of where mono depth errs. The DOM order is the visual order at every width.
 */
export function Stage({ doc, clip, frame, base, playing, setFrame, setPlaying, children }: {
  doc: ClipsDoc; clip: Clip; frame: number; base: string; playing: boolean;
  setFrame: (f: number) => void; setPlaying: (p: boolean) => void; children: React.ReactNode;
}) {
  const [view, setView] = useState<DreamView>("heat");
  const real = useRef<HTMLVideoElement>(null), heat = useRef<HTMLVideoElement>(null), gen = useRef<HTMLVideoElement>(null);
  useSeek([real, heat, gen], frame, clip.fps, clip.clip, !playing);
  useNativePlay({ real, dreams: { heat, gen }, view: view === "heat" ? "heat" : "gen", clipKey: clip.clip, frame, n: clip.n_frames, fps: clip.fps, playing, setFrame, setPlaying });
  const [failed, setFailed] = useState<string | null>(null);
  const rec = doc.recordings[clip.recording_key];
  const label = clipTitle(clip);
  const realKey = useId(), stageKey = useId();
  const past = isUnverifiable(clip, frame) && clip.unverifiable_from !== null, why = reasonText(clip);
  const video = (ref: React.RefObject<HTMLVideoElement | null>, which: "real" | "heat" | "gen", hidden: boolean, name: string, poster?: string, describedBy?: string) => (
    <video key={`${clip.clip}-${which}`} ref={ref} data-pane-video={which} src={mediaUrl(clip.assets[which], base)} poster={poster}
      muted playsInline preload="auto" hidden={hidden} aria-label={`${name}, ${label}`} aria-describedby={describedBy}
      onError={() => setFailed(which)} />
  );
  return (
    <section className="stage" aria-label="Stage">
      <div className="panes">
        <PlainNote id="stage.real" />
        <PlainNote id="stage.heat" />
        <figure className="pane" data-pane="real">
          <h2>The real tank, rebuilt from stereo</h2>
          <div className="pane-frame">
            {video(real, "real", false, "Real tank", undefined, realKey)}
            {/* past a cap or a loss both panes are grey or hatched end to end, which reads as a broken clip: say why, on the real pane's
                flat grey (it hides nothing there), and offer the way back */}
            {past && (
              <div className="pane-notice" role="status">
                <p>From frame {clip.unverifiable_from}, nothing here can be checked{why ? `: ${why}` : ""}.</p>
                {/* from frame 0 there is no checked frame to go back to: the line says why the panes are flat, and offers nothing */}
                {clip.unverifiable_from! > 0 && <button type="button" className="btn" onClick={() => { if (playing) setPlaying(false); setFrame(clip.unverifiable_from! - 1); }}>Back to the last checked frame</button>}
              </div>
            )}
          </div>
        </figure>
        <figure className="pane" data-pane="dream">
          <div className="pane-head">
            <h2>The dream</h2>
            <Segmented label="Dream view" hideLabel value={view} onChange={setView}
              options={[{ value: "heat", label: "Heat" }, { value: "bare", label: "Bare" }]} />
          </div>
          <div className="pane-frame">
            {video(heat, "heat", view !== "heat", "Dream with heat", mediaUrl(clip.assets.poster_heat, base), stageKey)}
            {video(gen, "gen", view !== "bare", "Dream, bare", mediaUrl(clip.assets.poster, base))}
          </div>
        </figure>
      </div>
      {failed && <p className="stage-error" role="alert">A clip could not be loaded ({failed}). Check the connection and reload.</p>}
      {children}
      <div className="key-strip" id={stageKey} role="group" aria-label="Key to the stage" data-view={view}>
        <ul className="marks">
          <li className="key-real" id={realKey}>
            <span className="swatch grey" style={{ background: rgbCss(doc.heat.unseen_rgb) }} aria-hidden="true" />
            <span>{realCaption(clip, frame)}</span>
          </li>
          {view === "heat" && <HeatMarks heat={doc.heat} />}
        </ul>
        {view === "heat" ? <HeatRamps heat={doc.heat} floor={rec.floor} /> : <p className="bare-note">The engine's own clip, unedited: the file exactly as it was made.</p>}
        <PlainNote id="stage.floor" />
        <FloorThumb key={rec.floor_map.preview} heat={doc.heat} src={mediaUrl(rec.floor_map.preview, base)} />
      </div>
    </section>
  );
}
