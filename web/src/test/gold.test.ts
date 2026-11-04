// Gold means one thing on this page: D above 3 (docs/DESIGN.md). The browser check (e2e) looks at pixels; this one looks at the source,
// so a stray var(--gold) is caught before it is ever drawn. The same rule covers the heat's colours: none of them is typed in the page.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseClips } from "../data/load";
import { readFixtureJson } from "./fixtureMedia";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");
const files = (dir: string): string[] => readdirSync(dir).flatMap((n) => {
  const p = join(dir, n);
  return statSync(p).isDirectory() ? (n === "fixtures" ? [] : files(p)) : /\.(css|tsx?)$/.test(n) && !/\.test\./.test(n) ? [p] : [];
});
const rel = (p: string) => relative(SRC, p);

/** Where gold may be used, and why. */
const ALLOWED: Record<string, string> = {
  "theme/tokens.css": "defines --gold, --gold-line and --on-gold",
  "scrubber/scrubber.css": "the D curve above 3, the departure tick, the dot while D is above 3",
  "plan/plan.css": "the path while D is above 3",
  "numbers/numbers.css": "the lead D figure while D is above 3",
};

describe("gold", () => {
  const all = files(SRC);
  it("is referenced only by the four places DESIGN.md names", () => {
    const using = all.filter((f) => /--gold|--on-gold/.test(readFileSync(f, "utf8"))).map(rel).sort();
    expect(using).toEqual(Object.keys(ALLOWED).sort());
  });
  it("is never typed as a colour anywhere but the tokens", () => {
    for (const f of all.filter((x) => rel(x) !== "theme/tokens.css"))
      expect(readFileSync(f, "utf8"), rel(f)).not.toMatch(/#c4922a|#d6a43c|#9a6a12/i);
  });
  it("the TSX decides gold only from D above the threshold", () => {
    const withGold = all.filter((f) => /\.tsx$/.test(f) && /\bgold\b|is-gold/.test(readFileSync(f, "utf8"))).map(rel).sort();
    expect(withGold).toEqual(["numbers/Numbers.tsx", "plan/PlanView.tsx", "scrubber/Scrubber.tsx"]);
  });
  it("is never the only thing telling D apart: the departure is also a tick and a number, so colour is never the sole carrier", () => {
    expect(readFileSync(join(SRC, "scrubber/Scrubber.tsx"), "utf8")).toMatch(/className="departure"/);
    expect(readFileSync(join(SRC, "numbers/Numbers.tsx"), "utf8")).toMatch(/cellText\(d, fmtD\)/);
  });
});

describe("the heat's colours are read from clips.json, never typed", () => {
  const heat = parseClips(readFixtureJson("clips.json")).heat;
  type Rgb = [number, number, number];
  const colours: Rgb[] = [...heat.positive, ...heat.negative, ...heat.floor_ramp].map(([, c]) => c as Rgb)
    .concat([heat.outline.rgb, heat.unseen_rgb, ...heat.unverified_hatch.greys.map((g): Rgb => [g, g, g])]);

  /** Every way a colour can be written: #rrggbb (and #rgb where it can be), rgb()/rgba() with commas or the CSS4 space syntax, and an
   *  [r, g, b] array literal as in a ramp. Returns the colours found in the text, one entry per form. */
  const findTyped = (text: string, list: Rgb[] = colours): string[] => {
    const found: string[] = [];
    const lower = text.toLowerCase();
    for (const [r, g, b] of list) {
      const hex = "#" + [r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("");
      if (lower.includes(hex)) found.push(`${hex}`);
      const short = hex.length === 7 && hex[1] === hex[2] && hex[3] === hex[4] && hex[5] === hex[6] ? `#${hex[1]}${hex[3]}${hex[5]}` : null;
      if (short && new RegExp(`${short}(?![0-9a-f])`).test(lower)) found.push(short);
      if (new RegExp(`rgba?\\(\\s*${r}[\\s,]+${g}[\\s,]+${b}\\b`).test(text)) found.push(`rgb(${r} ${g} ${b})`);
      if (new RegExp(`\\[\\s*${r}\\s*,\\s*${g}\\s*,\\s*${b}\\s*\\]`).test(text)) found.push(`[${r}, ${g}, ${b}]`);
    }
    return found;
  };

  it("no stop of the positive, negative or floor ramp, the outline, the unseen grey or a hatch grey is typed in any source file, tokens.css included (violet too)", () => {
    for (const f of files(SRC)) expect(findTyped(readFileSync(f, "utf8")), rel(f)).toEqual([]);
  });

  it("and the scan can fail: each way of typing a colour is caught (mutations the reviewer tried)", () => {
    expect(findTyped("a { color: rgb(124 64 184); }")).toContain("rgb(124 64 184)");                   // CSS4 space syntax
    expect(findTyped("a { color: rgba(124, 64, 184, .5); }")).toContain("rgb(124 64 184)");
    expect(findTyped(":root { --violet: #7c40b8; } .x { color: var(--violet); }")).toContain("#7c40b8");   // a token used through var()
    expect(findTyped("const ramp = [[0, [30, 12, 52]], [0.5, [124,64,184]]];")).toEqual(["[30, 12, 52]", "[124, 64, 184]"]); // an array in a .tsx
    expect(findTyped("a { color: #FFF; }")).toContain("#fff");                                          // the outline's white, shorthand
    expect(findTyped(".x { color: var(--stage-text); background: rgb(28, 25, 21); }")).toEqual([]);      // the stage's own ink is not a heat colour
  });

  it("the floor map's violet is among the colours checked", () => {
    expect(heat.floor_ramp).toHaveLength(3);
    expect(findTyped("#7c40b8")).toEqual(["#7c40b8"]);
  });
});
