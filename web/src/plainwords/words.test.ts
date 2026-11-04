// The plain-words layer's rules (the hub's docs/plain-words.md): every digit from clips.json or the page's own two thresholds, every
// spelled-out figure sourced, field words only inside quotes and every quote a label the page really shows, a reading level a
// 12-year-old manages, and every note and band placed exactly once where the plan put it.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseClips } from "../data/load";
import { D_REF, D_THRESHOLD } from "../lib/series";
import { readFixtureJson } from "../test/fixtureMedia";
import { CHAPTERS, NOTES, noteFor, PLAN_FAR, PLAN_FAR_AIR, UI, type Chapter, type NoteId } from "./words";

const here = dirname(fileURLToPath(import.meta.url));
const src = (rel: string) => readFileSync(join(here, rel), "utf8");
const told = (c: Chapter) => [c.title, ...c.band];
const NOTE_TEXT = [...Object.values(NOTES).flat(), PLAN_FAR_AIR];
const STORY = [...CHAPTERS.flatMap(told), ...NOTE_TEXT];
const EVERYTHING = [...STORY, ...Object.values(UI)];
const unquoted = (s: string) => s.replace(/"[^"]*"/g, "");
const all = EVERYTHING.join("\n");

// The real clips.json (gitignored, about 250 MB of assets beside it): present on Aaron's machine and in the scratch layout.
const ASSETS = process.env.DIVETWIN_ASSETS ?? join(here, "../../../runs/assets");
const have = existsSync(join(ASSETS, "clips.json"));
const real = have ? parseClips(JSON.parse(readFileSync(join(ASSETS, "clips.json"), "utf8"))) : null;
const fixture = parseClips(readFixtureJson("clips.json"));
/** The film's clip (call 81): in the fixture and in the real file alike. */
const film = fixture.clips.find((c) => c.clip === "freshwater-basicEnhance__gen45__N__5s")!;

describe("honest numbers", () => {
  /** "3D" is a word, not a figure. */
  const digits = (s: string) => [...s.replace(/\b3D\b/g, "").matchAll(/\d+(?:\.\d+)?/g)].map((m) => m[0]);

  it("every digit is one of the page's two thresholds (D at 1 and 3), or the count of films", () => {
    const thresholds = new Set([String(D_REF), String(D_THRESHOLD)]);
    const rest = EVERYTHING.flatMap(digits).filter((d) => !thresholds.has(d));
    expect(rest, "digits other than the thresholds").toEqual(["35"]);
    expect(all).toContain("There are 35 films here");
    expect(all).toMatch(/At 1, the dream is as close to the real tank/);
    expect(all).toMatch(/At 3, the tank has changed shape/);
  });

  it.skipIf(!have)("the counts come from the real clips.json: 35 films, five recordings, two programs, three kinds of request", () => {
    const doc = real!;
    expect(String(doc.clips.length)).toBe("35");
    const count = (k: "recording_key" | "engine" | "prompt") => new Set(doc.clips.map((c) => c[k])).size;
    expect([count("recording_key"), count("engine"), count("prompt")]).toEqual([5, 2, 3]);
    expect(all).toContain(`There are ${doc.clips.length} films here: five recordings, two programs, three kinds of request.`);
  });

  it("\"just under four seconds\" is the film's departure: frame 88 at 24 fps", () => {
    const s = film.first_D3! / film.fps;
    expect(s).toBeGreaterThanOrEqual(3.5);
    expect(s).toBeLessThan(4);
    expect(all).toContain("\"D\" passes 3 just under four seconds in");
    if (real) expect(real.clips.find((c) => c.clip === film.clip)!.first_D3).toBe(film.first_D3);
  });

  const WORDS: Record<string, number> = { three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, twenty: 20, hundred: 100, thousand: 1000 };
  /** Spelled-out figures and where each comes from ("two" is left out: two eyes and two tanks are not data). */
  const SPELLED: Record<string, { value: number; source: string }> = {
    three: { value: 3, source: "the prompts D, B and N (clips.json)" },
    four: { value: Math.ceil(film.first_D3! / film.fps), source: "the film's departure, just under four seconds" },
    five: { value: 5, source: "the recordings (clips.json)" },
  };
  it("every spelled-out figure is sourced", () => {
    const bad: string[] = [];
    for (const s of STORY) for (const m of s.toLowerCase().matchAll(new RegExp(`\\b(${Object.keys(WORDS).join("|")})\\b`, "g"))) {
      const known = SPELLED[m[1]];
      if (!known || known.value !== WORDS[m[1]]) bad.push(`"${m[1]}" has no source: ${s}`);
    }
    expect(bad).toEqual([]);
  });
});

describe("plain words", () => {
  // Field words may appear only in quotes, naming a label on the page ("The page calls this ...").
  const JARGON = /\b(median|metrics?|benchmark|residual|disparity|reconstruct\w*|depth|mono|monocular|pose|ICP|PnP|RANSAC|su|stereo|scale|shift|heat|pixels?|models?|AI|algorithm|dataset|neural|threshold|verif\w*|extrapolat\w*|render\w*|intrinsics|atlas|relief|unverifiable|departure|floor)\b|[ρα×±]/i;
  const LETTERS = /\b[DV]\b/;                   // "D" and "V" are the page's labels: only in quotes
  it("field words, and the letters D and V, appear only inside quotes", () => {
    const bad = EVERYTHING.filter((s) => JARGON.test(unquoted(s)) || LETTERS.test(unquoted(s)));
    expect(bad.map((s) => `${(unquoted(s).match(JARGON) ?? unquoted(s).match(LETTERS))![0]}: ${s}`)).toEqual([]);
  });
  it("the rule bites (the draft's unquoted D and heat would have failed it)", () => {
    expect(LETTERS.test(unquoted("In this film, D passes 3 just under four seconds in."))).toBe(true);
    expect(JARGON.test(unquoted("Its colours are rougher than the heat's, so read the heat for the details."))).toBe(true);
  });

  /** Flesch–Kincaid grade over the story's sentences (titles aside), with the explorer's syllable heuristic. */
  const syllables = (w: string) => {
    const s = w.toLowerCase().replace(/[^a-z]/g, "");
    if (!s) return 0;
    if (s.length <= 3) return 1;
    const t = s.replace(/(?:[^laeiouy]es|ed|[^laeiouy]e)$/, "").replace(/^y/, "");
    return Math.max(1, (t.match(/[aeiouy]{1,2}/g) ?? []).length);
  };
  const sentences = [...CHAPTERS.flatMap((c) => c.band), ...NOTE_TEXT]
    .flatMap((p) => p.split(/(?<=[.!?])\s+/)).map((s) => s.split(/\s+/).filter((w) => /[a-z0-9]/i.test(w)));
  const words = sentences.flat();
  const grade = 0.39 * (words.length / sentences.length) + 11.8 * (words.reduce((n, w) => n + syllables(w), 0) / words.length) - 15.59;
  const average = words.length / sentences.length, longest = Math.max(...sentences.map((s) => s.length));

  it(`reads at grade 6 or below (Flesch–Kincaid ${grade.toFixed(2)})`, () => {
    expect(grade).toBeLessThanOrEqual(6);
  });
  it(`short sentences: 14 words on average (${average.toFixed(1)}), none over 25 (longest ${longest})`, () => {
    expect(average).toBeLessThanOrEqual(14);
    expect(sentences.filter((s) => s.length > 25).map((s) => s.join(" "))).toEqual([]);
  });
  it("no draft notes", () => {
    expect(all).not.toMatch(/Draft|TODO|TBD/);
  });
  it("Air has no far wall (call 28): its plan note says the far line is as far as the camera could see", () => {
    expect(NOTES.plan).toContain(PLAN_FAR + " When the line turns gold, the dream has stopped being the tank.");
    const air = noteFor("plan", "air").join(" ");
    expect(air).not.toMatch(/far wall/i);
    expect(air).toContain(PLAN_FAR_AIR);
    expect(noteFor("plan", "freshwater")).toBe(NOTES.plan);
  });
});

describe("placement", () => {
  const files = (dir: string): string[] => readdirSync(join(here, dir), { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? (e.name === "plainwords" || e.name === "test" ? [] : files(`${dir}/${e.name}`))
      : /\.tsx$/.test(e.name) && !e.name.includes(".test.") ? [src(`${dir}/${e.name}`)] : []);
  const code = files("..").join("\n");

  it("every note is placed exactly once", () => {
    const counts = (Object.keys(NOTES) as NoteId[]).map((id) => [id, code.split(`<PlainNote id="${id}"`).length - 1]);
    expect(counts.filter(([, n]) => n !== 1)).toEqual([]);
  });
  it("the invite sits under the title row; chapter 1 above the stage, 2 above the evidence row, 3 above the statement", () => {
    const app = src("../App.tsx");
    const at = (s: string) => { const i = app.indexOf(s); expect(i, s).toBeGreaterThan(-1); return i; };
    expect(at('slot="invite"')).toBeGreaterThan(at('className="title-row"'));
    expect(at('slot="chapter-1"')).toBeGreaterThan(at('slot="invite"'));
    expect(at("<Stage ")).toBeGreaterThan(at('slot="chapter-1"'));
    expect(at('slot="chapter-2"')).toBeGreaterThan(at("</Stage>"));
    expect(at('className="evidence"')).toBeGreaterThan(at('slot="chapter-2"'));
    expect(at('slot="chapter-3"')).toBeGreaterThan(at('className="evidence"'));
    expect(at("<Statement ")).toBeGreaterThan(at('slot="chapter-3"'));
  });
  it("the three chapters have distinct anchors, in order", () => {
    expect(CHAPTERS.map((c) => c.id)).toEqual(["plain-words-1", "plain-words-2", "plain-words-3"]);
  });
});
