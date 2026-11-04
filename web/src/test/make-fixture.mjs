// Rebuilds src/test/fixtures/ from the real runs/assets: four real clips, trimmed from clips.json, their recordings, and the
// small files the tests decode. Nothing is edited by hand: run it again after a `cli.py assets` rebuild and re-run the tests.
//   node src/test/make-fixture.mjs [assetsDir]
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = process.argv[2] ?? join(here, "../../../runs/assets");
const out = join(here, "fixtures");

// Why these four: the film's clip (a departure at f88), a pellets clip past its travel cap (V is 0.0 in the data past it),
// a clip whose path was lost (and a tracked moving object), and a clip whose D never passes 3.
const IDS = [
  "freshwater-basicEnhance__gen45__N__5s",
  "saltwater-pellets__gen45__N__5s",
  "air__wan22__N__5s",
  "air__gen45__D__5s",
];

const doc = JSON.parse(readFileSync(join(src, "clips.json"), "utf8"));
const clips = IDS.map((id) => {
  const c = doc.clips.find((x) => x.clip === id);
  if (!c) throw new Error(`${id} is not in ${src}/clips.json`);
  return c;
});
const conditions = [...new Set(clips.map((c) => c.recording_key))];
const trimmed = { ...doc, clips, recordings: Object.fromEntries(conditions.map((k) => [k, doc.recordings[k]])) };
mkdirSync(out, { recursive: true });
writeFileSync(join(out, "clips.json"), JSON.stringify(trimmed, null, 1) + "\n");

const copy = (rel) => {
  mkdirSync(dirname(join(out, rel)), { recursive: true });
  copyFileSync(join(src, rel), join(out, rel));
};
for (const c of clips) copy(c.assets.path);
for (const k of conditions) copy(trimmed.recordings[k].plan);
copy(trimmed.recordings["freshwater-basicEnhance"].tank_relief.png);       // the one PNG16 the decoder test reads for real
console.log(`fixture: ${clips.length} clips, ${conditions.length} recordings -> ${out}`);
