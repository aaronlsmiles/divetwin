# Dive Twin: web

Vite 8, React 19, TypeScript, Vitest, Playwright, react-three-fiber. Design: `../docs/DESIGN.md`. The plan: `~/projects/studio/prototypes/plans/p04-dive-twin/plans/sub-plan-c-2026-11-04.md`.

```bash
npm install
npm run dev        # http://localhost:5173; serves ../runs/assets at /media/ (the real clips, about 250 MB, gitignored)
npm test           # Vitest: units, components, the four-clip fixture, the page-level figures test (10 tests read the real runs/assets and skip without it)
npm run build      # tsc --noEmit && vite build
npm run e2e        # Playwright at 1440 and 390, light and dark, against the real runs/assets (starts vite on :5299; E2E_PORT=<n> to change)
```

## Data

The page reads one contract, `runs/assets/clips.json` (written by `pipeline/assets.py`), and the files it names: `clips/<id>/{gen,heat,real}.mp4`, `path.json`, `relief.png`, `tank_relief.png`, and `recordings/<c>/{start.jpg,plan.json,floor_preview.jpg}`. It never reads `runs/clips.json`.

- **Dev and `vite preview`:** `vite/media-dev.ts` serves `runs/assets` at `/media/` (Range-aware, follows symlinks). `DIVETWIN_ASSETS=<dir>` points it elsewhere.
- **Production:** `VITE_MEDIA_BASE` at build time, the media host's `divetwin/v1/` prefix. Unset in a production build, the page says there is no media. Phase 6 sets it; nothing here uploads or deploys. Check a build against the real files first: `VITE_MEDIA_BASE=/media/ npx vite build && npx vite preview --port 5393`.
- **Tests:** `src/test/fixtures/` is four real clips trimmed from `clips.json` by `node src/test/make-fixture.mjs` (never edited by hand; run it again after an assets rebuild).

## Capturing a frame for the film (task 5.1)

Play is native video playback, so a recording of it is as smooth as the browser's; for a **deterministic** still or a frame-exact cut, do not record Play. Open `/?clip=<id>&f=<n>`, wait until all three videos have finished seeking to the middle of frame `n` (`!video.seeking`, `readyState >= 2` and `currentTime == (n + 0.5) / 24` on each: `waitForFrame` in `e2e/helpers.ts`), then capture. All three videos always seek when the page is paused, so the real pane, the heat and the bare clip are on the same frame. The derived `heat.mp4` and `real.mp4` have a keyframe every 12 frames or less, so each seek decodes at most 12 frames.

## Rules the tests hold

- Every numeral on the page traces to `clips.json` or to one of four named thresholds (`src/test/facts.ts`).
- `unverifiable` is never `0.00`: the pipeline writes `V = 0.0` after a travel cap, and the page checks `unverifiable_from` first.
- Gold means D above 3 and nothing else (`src/test/gold.test.ts` reads the source; the e2e counts pixels), and no heat colour is typed in the page: the ramps, the hatch, the outline, the unseen grey and the floor map's violet all come from `clips.json`.
- Units are su (uncorrected stereo units), never mm.
- The plain-words layer (`src/plainwords/`, the hub's `docs/plain-words.md`) is additive: with it off the page is unchanged. `words.test.ts` holds its digits (D at 1 and 3, the 35 films from the real `clips.json`, "just under four seconds" for f88 at 24 fps), field words only in quotes, every quote a label the page shows, Flesch–Kincaid grade 6 or below, sentences of 14 words on average and none over 25, and each note placed once. `e2e/plain.spec.ts` walks the trail and checks AA contrast, Tab order, nothing over the media, and no overflow at 390 or with text at 200 %.

## The plain-words layer (task 4.4)

The invite sits under the title row; the three chapter bands sit above the stage, above the evidence row and above the statement; "Next" scrolls to the next band and focuses it. Notes are pinned beside the real pane, the dream, the floor map, the scrubber, the plan view, the relief, V, and the statement's "one scale and one shift" and "stereo". On the stage (ink in both themes) the notes take the pencil's ink-ground values. `?plain=1` opens it and `?plain=0` closes it; the reader's choice is remembered (`dt-plain`), and with the layer on every link into another studio site carries `?plain=1`.

## Picking up from here

- **Design pass (task 4.5):** done 4 Nov; every decision is in `../docs/DESIGN.md` ("Design pass, 4 Nov"), with what it leaves for 4.6.
- **Verify pass (task 4.6):** done 4 Nov; the results and every fix are in `../docs/DESIGN.md` ("Verify pass"). The checks stay as tests: `e2e/verify.spec.ts` (Tab and pointer sweeps, sync on a throttled CPU, axe, text at 200 %, reduced motion, the 4.6 items) and `e2e/worst.spec.ts` plus `src/test/worst.test.tsx` (`break-ui`: the worst data, from `src/test/worst.ts`, entering at the fetch boundary).
- **Pipeline prerequisite:** the page needs the `assets` rebuild of task C0 (the floor map's ramp in the palette, the cell intrinsics in each relief block, the short-GOP videos). Without `floor_ramp` the loader refuses the file and says which key is missing.
