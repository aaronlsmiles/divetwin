# Dive Twin: design direction

Set 4 Nov 2026 (task 4.1) with `design-taste-frontend`, app-screens run. Style **achromatic-ledger**, seed 1916747175 (kind `markets`, screen `detail`), palette and type kept from the StillDrawn Explorer (`../stilldrawn-explorer/docs/DESIGN.md`), so the two studio explorers read as one family. The sheet is in `.taste-skill/app/direction.json`.

**Redraw: the shell.** The sheet dealt an open plane with a labelled sidebar. This is a viewer with one destination, though, and the stage needs the full width, so it uses the **no-sidebar** shell (app-screens §3.1, "for reports, viewers and products with few destinations"). The explorer made the same redraw for the same reason.

## The screen's one question

**"When does the dream stop being the tank it started in?"**

- **What is biggest:** the stage. The real tank and the dream sit side by side at the same frame, and under them is the scrubber, whose track is the D curve.
- **The finding** sits on the line under the title and is computed from `clips.json` per clip, never typed. For the default clip it reads: "D passes 3 at frame 88 (3.7 s), 711 su in; every pixel still verified (V 1.00)". The template is: departure frame (`first_D3`), the distance at that frame from `path`, and V at that frame. When a clip has no departure, the line says so ("D stays under 3; peak 1.9 at frame 120"). When the clip ran out of verification first, it says where (`unverifiable_from`, `lost_from`).
- **The page opens on the finding:** basicEnhance · Gen-4.5 · prompt N · 5 s (the film's clip, call 81), with the cursor parked on its departure frame, f88.
- **The most frequent job** is to scrub, then to choose another clip. The clip picker sits in the title row and comes first in Tab order, because Tab follows the page as it reads; the scrubber has its own way in, the second skip link, "Skip to the scrubber" (the second Tab stop). Decided in task 4.6; see "Verify pass" below.

## The face and the signature element

- **The face: the stage is a darkroom.** The two video panes, the scrubber and the relief always sit on the ink well (`--stage`, the explorer's dark ground `#1c1915`), in both themes. The page chrome around them follows the theme toggle (paper or ink). The heat ramps begin dark at r = 0, so on paper an agreeing tank would look like a hole; on ink, agreement is quiet and a lie glows. This is what the plan meant by "ink ground".
- **The signature element: the plan view.** A drawing of the tank from above: the side walls, the far wall at `far_end`, the recovered path as one ink line from the camera's start, and a cursor at the current frame.
  - Where the path is lost (`lost_from`) it turns to a dashed grey and stops; it is never extrapolated.
  - Past the trusted range (`trusted_travel_su`, pellets only) it turns grey.
  - Where D > 3 the path is gold.
  - The far wall is drawn at its measured distance. A dream that passes it is visibly outside the tank: no other viewer has that picture, and it is the dive told as a map.
- **Second to it: the scrubber is the D curve.** The range input's track is D(k) drawn over 121 (or 241) frames, on a piecewise scale (task 4.6: 0.5 to 3 at full slope, 3 and above at half of it). It has a 1 px dashed reference at D = 1 (no worse than mono depth on the real tank) and at D = 3 (the tank has changed shape). The curve is ink up to 3 and gold above it. A hatched span shows where verification ran out. One control, two jobs: the cursor and the evidence.

## Colour: what the gold means here

The explorer used gold for the selection. **On this page gold means one thing only: D above 3.** It appears on:
- the D curve above the 3 line;
- the plan view's path while D > 3;
- the lead D figure while the cursor sits above 3 (a gold fill under ink text in light, gold text on ink);
- the departure tick on the scrubber.

Nothing else is ever gold. So:

- **Selection is ink.** A 2 px `--text` underline on the current option, the `--active` fill on the chosen table row, and an ink cursor line.
- **The focus ring is ink, not gold** (a departure from the explorer): a 3 px `--text` outline with a 2 px offset. On the stage it is `--stage-text`.
- **The heat is the pipeline's, read from `clips.json`, never retyped.** `heat.palette_json()` defines two sequential ramps, both monotone in lightness with the same steps, chosen by the sign:
  - warm oranges where the dream reads **nearer** than the tank;
  - blues where it reads **farther**.

  Each ramp is a sequential ramp, as the plan asks. The sign only picks which one, and neither is a rainbow. The rest of the key:
  - the 45° grey hatch means "unverified";
  - a white 2 px outline means "a tracked moving object, drawn but not counted in D";
  - the flat grey `#707070` means "no real camera saw it".

  The legend swatches are built from the same JSON as the marks.
- **The floor map keeps its own violet ramp** (`FLOOR_RAMP`). It is display only and carries no sign, so it must not look like the residual. The house ban on violet is for chrome accents; this is a raster inside one figure, and it stays there.
- **Tokens:** the explorer's table, unchanged (ground, surface, raised, border, rule, control, text, muted, faint, context, gold, gold-line, on-gold, pencil-wash, pencil, pencil-ink). Three are added:

| Role | Both themes | Notes |
|---|---|---|
| `--stage` | `#1c1915` | the darkroom well under the media, the scrubber and the relief |
| `--stage-text` | `#ecebe6` | labels on the stage (13.1:1) |
| `--stage-muted` | `#b3aa9e` | ticks and captions on the stage (6.8:1) |

## Type, space, motion

As the explorer:
- **Type:** Geist 400/600/800, scale 12 / 14 / 16 / 24. The lead D figure is the one exception at 32 / 600: it answers the screen's question. Tabular figures on every number. Geist Mono only for the seed and hashes in the provenance block.
- **Corners and space:** square corners. A 4 px base, one 16 px gutter, a page margin of 24 at 1440 and 16 at 390, controls 32 px tall (44 px touch targets on phones).
- **Units:** every distance is in su, set as a grey suffix: "711 su". Never millimetres. The unit is named once in full in the statement: "uncorrected stereo units (su)".
- **Motion:** feedback only, with no entrances.
  - Scrubbing is immediate: no easing on the cursor, and all three panes seek to the same frame.
  - Play steps the frames at 24 fps across every pane at once.
  - The relief's orbit eases (`--ease`, 240 ms) and is limited to about ±25°.
  - `prefers-reduced-motion` stops the autoplay, makes the orbit instant, and shows the relief as a still.

## The screen, at 1440 × 900

Grid: 1440 − 2 × 24 = 1392 = 12 × 101 + 11 × 16 (1212 + 176 = 1388, leaving 4 px slack spread across the gutters; the sub-plan fixes the exact column sum).

1. **Top bar, 48 px.**
   - Left: the mark and the wordmark "Dive Twin". The mark is a 16 px square, the tank from above, with an ink path entering at the bottom and leaving through the top wall.
   - Right: "About this measure" (an anchor to the statement), the dataset DOI link, and the theme toggle.
2. **Title row.**
   - The h1 is the clip's breadcrumb at 24/600: "Freshwater, enhanced · Gen-4.5 · prompt N · 5 s" (the length is in the h1 because three clips have a 10 s twin; sub-plan C delta 14). Recording names are the condition's short name, never the dataset's long file name.
   - Under it is the finding line at 16 px in `--muted`.
   - Right of the title is the clip picker: three segmented controls in one row, for recording (5), engine (2) and prompt (D · B · N). A length switch (5 s · 10 s) shows only where a 10 s dive exists.
3. **The stage, full width, on `--stage`.**
   - Two panes at equal width, 688 × 387 each (16:9).
   - The left pane is **"The real tank, rebuilt from stereo"** (`real.mp4`). Its caption reads "grey: no real camera looked here".
   - The right pane is **"The dream"**. A two-way switch flips it between "Heat" (`heat.mp4`, the default) and "Bare" (`gen.mp4`), and its caption is the heat key in words with the ramp swatches.
   - The dream pane's caption row holds the heat key and, beside it, the floor map thumbnail (192 × 108, "where mono depth already errs on the real tank; display only, the same for every frame", its violet ramp from `clips.json`), shown in both Heat and Bare (call 85; sub-plan C delta 13). At 760 px and below the thumbnail sits under the key.
   - Under both panes is the scrubber at 96 px: the D curve as the track, a play button, the frame and time readout ("f88 · 3.67 s"), and arrow keys for ±1 frame (Shift for ±12).
   - The start frame sits in the scrubber's left gutter as a 64 px thumbnail, captioned "the photograph both started from".
4. **The evidence row, 12 columns as 4 + 4 + 4.**
   - **The plan view** (signature, SVG, square), titled "Where the camera went".
   - **The relief** (react-three-fiber), titled "The two tanks as surfaces", with the residual as vertex colour.
   - **The numbers**, one divided container:
     - **D now** as the lead figure, with the floor beside it in words ("1 = no worse than mono depth on the real tank");
     - **V now**, with its curve as the second track under the D curve rather than a sparkline;
     - **distance travelled**, in su, with the far end's distance as the comparison;
     - **departure frame**;
     - **path agreement**, in su or as a share of max(travel, 200 su), never as an error bar (call 78).
   - Each block's header and first content is visible on the first screen.
5. **Below the fold:**
   - **The statement** (§7, verbatim or close).
   - **The wall test's limit,** said plainly (call 82): "a path anchored to the tank cannot follow a dream out through the far wall; the first sustained D above 3 marks the departure".
   - **Per-clip notes from the findings,** for example air Wan N's mask, which starts on a dark flash (call 84).
   - **All 35 clips as one table:** recording, engine, prompt, length, D and V at 5 s (and at 10 s), departure frame and travel. Rows are clickable and load the stage. A cell with no value shows a grey dash, and a cell past the cap says "unverifiable", never 0.00 (call 85).
   - **Credits:** the dataset (CC BY, DOI 10.5281/zenodo.16753748), the models and their licences from `pipeline/MODELS.md`, and the camera named as a ZED Mini.
6. **The plain-words layer** (4.4) is additive, in blue pencil, as on the explorer and studionephele.com: an invite under the title row, three chapter bands, and notes pinned beside "scale and shift", "stereo" and "the heat map".

## The phone, 390

- **Top bar:** the wordmark, then a menu holding About, the DOI and the theme toggle.
- **The title** at 20 px, then the finding line. The picker becomes one row of three selects.
- **The stage** stacks the real pane over the dream pane, each 358 × 201, both on the ink well, followed by the scrubber at full width.
- **The numbers** follow as a 2-column grid with D leading at full width, then the plan view at full width, then the relief.
- **The relief** is a still unless tapped. Its orbit runs only on a drag inside the canvas, so it never traps the page's scroll.
- **The clip table** becomes two-line rows: line 1 is the breadcrumb and D; line 2 is V, the departure frame and the travel.

## Blue does two jobs (decided 4 Nov, hub call 86)

The house keeps blue for the plain-words pencil, and the heat's "reads farther" ramp is blue too; task 3.5 found that the dreams that flare mostly read farther. Aaron's call: **keep both, kept apart by place.** Pencil appears only on wash bands and pinned notes, never over media; heat blue appears only inside the frames and their key, which names the sign in words. **Task 4.5's design pass checks it on the built page** and decides whether the negative ramp would be better teal (one CPU-only `assets` rebuild, about 30 min, no spend; the heat videos and posters change). **Checked 4 Nov (hub call 89): blue stays;** the reasons are in the design pass below.

## Design pass, 4 Nov (task 4.5)

Run with `impeccable` (critique, audit, layout, typeset, polish), then `improve-animations` and the `review-animations` standard, then the `design-taste-frontend` inspector. Aaron's standing go (hub call 88) covered it; where a skill would have asked, the decision below was made against this file. Each line says what changed and why. Where it departs from the sections above, this section wins.

**The stage**
- **The scrubber sits straight under the panes, and one key strip sits under the scrubber.** The most frequent job is to scrub, and the D curve reads against the frames directly above it. Before, a three-column caption about 210 px tall stood between the frames and the scrubber, and left dead ink under the real pane.
- **The key strip covers the whole stage, in one row at 1440:**
  - the marks (the real pane's grey first, then the heat's hatch and outline);
  - the two ramps, one line each;
  - the map of where mono depth errs, with its words beside it.

  This replaces the per-pane captions. The real video names its line with `aria-describedby`; the heat video names the strip.
- **The floor map is 144 × 81**, three quarters of call 87's 192 × 108. At that size the strip is one row of 81 px. The full size would cost a second row and push the evidence row back below the fold.
- **The stage has a 1 px edge in the dark theme** (`--stage-edge`, `#3d3831`; transparent on paper). The darkroom stays `#1c1915` in both themes. On ink it would otherwise melt into the ground. The plain-words bands and notes keep their own wash, so they stand apart on both.
- **The scrubber's axis labels sit in a 40 px gutter right of the track** (36 px on a phone): "D = 1", "D = 3" and "V". They are painted last, so they never sit under the curve. Their centres are at least 11 px apart even when D runs to the top of the scale, so they never collide. The track itself stays 96 px.
- **The key row says what gold means where gold is drawn:** "D the curve, gold above 3". The warm heat ramp comes within ΔE76 ≈ 14 of dark-mode gold (at t ≈ 0.7). It never meets gold as a shape, though: heat is an area inside the frames, and gold is only a stroke, a tick, a dot or the lead figure. The words close the gap on the page side, and the gold token is unchanged.
- **Past a cap or a loss, the real pane says why.** It reads "From frame n, nothing here can be checked: …" and offers "Back to the last checked frame". The line sits on the pane's own flat grey, which it hides nothing of. Without it, two all-grey panes read as broken video.
- **The relief's camera moved closer:** position (0, 1.2, 2.7), aimed at (0, 0.25, −4); it was (0, 1.4, 5) aimed at (0, 0, −4). The surfaces now fill most of the frame instead of about half. Checked on four recordings and at full orbit; Air's dream still runs past the top, which is the dream itself.

**The first screen**
- **The plain-words invite sits under the finding, in the title's own column.** It was a full-width row. The DOM order is unchanged: under the title, before the stage.
- **The evidence row's headers are on the first screen at 1440 × 900.** Their bottoms are at 845 once the invite is answered (was 966), with the plan's far-wall label and "D now" in view; on a first visit, with the invite showing, they are at 896. The row starts at 808 against an aim of about 780. The last 28 px would cost the floor map's size or the 96 px scrubber, so both stay. An e2e test holds both states.
- **The page's top padding is 16 px and the stage's inner gap is 12 px.** The pane heads are 28 px on a desktop, like the scrubber's controls; they stay 44 px on a phone.

**Phone and order**
- **The picker is two rows of selects:** the recording on its own row, then engine and prompt. The names are long ("Freshwater, enhanced"), and three equal selects cut the first to "Freshwa". This departs from "one row of three selects" above.
- **"The dream" stays on one line:** the Heat/Bare switch keeps its own width on a phone.
- **The evidence row's DOM order follows its layout** (`ui/useMedia.ts`): the numbers come first on a phone, and the plan view first on a desktop. It was CSS `order`, which made Tab and screen-reader order differ from what is seen. Nothing is reordered with CSS now.
- **Both pane notes come before both panes**, so the grid's row flow sets each above its pane, and on a phone the two panes stay together. The scrubber's note follows the scrubber, so with the layer on nothing comes between the panes and the line under them. V's note follows V's value, inside V's block.
- **The numbers on a phone:** path agreement takes the whole width, since its note is the longest. With plain words off, the departure does too, so no cell sits beside a gap. Cells align to the top, and the inner box is gone: the panel is the container.
- **The h1 breaks only at its " · " separators,** never inside "Gen-4.5".

**Type and polish**
- **A D above 3 in the table is set in 600 weight**, never gold, so departures can be scanned down the column.
- **The current row's units, dashes and phone labels use `--muted`.** `--faint` on `--raised` is 3.9:1 on paper.
- **Prose is set at 60ch**, about 75 characters of Geist at 14 px. At 70ch the measure ran to 96–104 characters.
- **The plan view's labels are 12 px** (they were 11), and every distance uses a true minus: −231 su, −200.
- **The plan view keeps a path that backs out past the start** (Freshwater · Wan 2.2 · B, −212 su) inside the square, with its cursor. Its scale reaches below 0, and a 44 px left gutter means no tick label is clipped. Air's longer far-end label sits over the wall's end when it would run off the square.

**Motion** (the `improve-animations` audit, read-only, then applied here)
- **The motion was already right:** no entrances, hover colour only under a fine pointer, and press feedback at scale 0.97 over 160 ms on `--ease`.
- **One fix:** a pressed toggle (Play/Pause) eased its fill for 160 ms when clicked under a hovering pointer. It now changes state at once, and only the press scales.
- **Measured on the preview build:**
  - The scrubber's cursor moves within about 5 ms.
  - All three panes land on the new frame in 85–106 ms. That is decode time, with a keyframe every 12 frames (Home, which lands on a keyframe, takes 12–40 ms). There is no debounce in the code.
  - The relief's orbit eases with τ = 0.08 s and settles in about 240 ms. It can be interrupted, since it follows a target, and is instant under reduced motion.
  - Smooth scrolls (a table row, plain words' "Next") fall back to instant under reduced motion.

**Blue stays (call 86 checked on the built page; hub call 89).** The heat's "reads farther" ramp stays blue, and there is no assets rebuild.
- What teal would gain: it would pull the heat away from the pencil (ΔE76 to pencil from about 5–6 to 42).
- What it would cost: the separation between the two signs, which is what the heat exists to show. It drops by about 15% for normal vision and 25–40% under deuteranopia and protanopia (Machado simulation, ΔE76 at t = 0.2–1).
- On the built page, pencil sits only on its wash with ink text, never over a frame.

**Critique scores.** Before: 28/40, with three P1s: the plan view clipped a reversing path, the scrubber and evidence row were below the fold, and you couldn't scrub and watch on a phone. After: 28/40 from a fresh reviewer with different findings. Its two P1s (dead frames read as broken; the plain-words layer split the panes from the scrubber) are fixed above.

**Inspector WARNs, defended** (`inspect.mjs --app`, 1440, 768 and 390: 0 FAIL)
- `no-poster` (real pane): the asset contract has no real-pane poster, and a stand-in would show a picture that isn't that pane's frame.
- `colour-sprawl` (14%): it is the media, the heat video and the floor raster, which are pictures rather than chrome.
- `ragged-row`: the three cards hold different things (a square plan, a square relief, a five-block list). Equal heights would mean a blank band, which is the `panel-void` it replaced, or padding content.
- `numeric-align` (390): the phone rows are two-line labelled records. Each D and V cell has the same label and tabular x.xx figures, so the digits already line up.

**Left for 4.6:** all of it was taken in task 4.6, each with its reasoning in "Verify pass" below (the title row's reflow, the 768 evidence row, the `THREE.Clock` notice, the phone table's breadcrumb, Tab order, and the reviewer's three P2s).

## Verify pass, 4 Nov (task 4.6)

Run by Sonnet 5.5 · high, on Aaron's standing go (hub call 88). The pass is Playwright at 1440 and 390, light and dark, against the real `runs/assets`; the checks are tests, so they stay. Where it departs from the sections above, this one wins.

**What it measured** (`e2e/verify.spec.ts`, `e2e/worst.spec.ts`, `src/test/worst.test.tsx`)
- **Every control, by keyboard and by pointer.** A Tab sweep walks the whole page (61 stops at 1440, 58 at 390) and asserts that each stop has a name, a visible ring (the range and the radios are invisible natives, so the ring is on the track box and the segment) and a place on the page; there is no positive `tabindex`. A pointer pass clicks the scrubber's track, Play and Pause, Heat and Bare, every picker control, a table sort and a table row, the theme toggle, the menu on a phone, About and the DOI link. The console is clean throughout (only the allow-listed notices in `e2e/helpers.ts`).
- **Sync on a throttled CPU.** At 390 px with `Emulation.setCPUThrottlingRate` 4:
  - After eight scrubs (60, 120, 0, 37, 88, 5, 100, 119), the picture each pane presented next (a visible pane through `requestVideoFrameCallback`, the hidden one through `seeked`) was the chosen frame on all three videos every time, so 0 frames apart.
  - During Play, the callbacks of two videos in one animation frame share a timestamp, so they saw the same screen. The media times they report are the pictures on it. Over 53 to 72 such screens per view, the two videos were never more than 1 frame apart (about 90 % at 0 and the rest at 1, the lag of a frame that arrives a moment later on one of them). Each video was handed 119 to 121 of the 121 frames. Both views, Heat with the real pane and Bare with the real pane, hold.
  - A busy main thread coalesces callbacks, so only a third to a half of the screens could be paired under the throttle. The test asks for 20 and for no pair over 1.
- **Axe** (`@axe-core/playwright` 4.14.0, all default rules): 0 violations of any impact, not only serious and critical, on the default state, with plain words on, and on a clip past its cap (hatched, with the real pane's notice), at both sizes and in both themes. Before this pass it found one (below).
- **Text at 200 %.** At 1440, with every type token doubled (the layer's own convention) and plain words off and on: no sideways scroll, no element clipping its text, and nothing outside its panel. At a 720 px viewport (the page zoomed to 200 %) and 360 px (400 %): no sideways scroll.
- **Reduced motion.** Nothing autoplays, `document.getAnimations()` is empty, every checked transition is 0 s, the relief is a still with an "Orbit the surfaces" button (asking arms the canvas), a pick from the table scrolls the stage into view at once, and Play still plays (it is content, not decoration).

**`break-ui`: the worst realistic data**, entering at the page's one data boundary (the `clips.json` and `path.json` it fetches, and 404s on the relief atlas and the floor preview), never in a component. The fixtures are `src/test/worst.ts`, shared by the Vitest and Playwright trails; nothing in `src/` imports them.

| Case | How it renders now |
|---|---|
| A D off the scale (40 from the departure on) | The curve runs to the top edge of its track and stops there, never past it (a test reads every point). The lead figure, the readout, the slider's spoken value and the table cell all say 40.00 and fit their boxes. Gold, as for any D above 3. |
| A recording name of 60 characters ("Saltwater pellets, second deployment, the long northern tank") | Whole in the title (it wraps inside its crumb on a phone), in the picker (the option is as wide as its name; the row wraps below the title at 1440; the phone's select shows the start of it and the title above carries the whole), in the table and in the document title. No sideways scroll at 1440 or 390. |
| A missing relief atlas (404) | The relief panel says "The depth atlas could not be loaded." and, under it, that everything else still works. Scrub, plan view, numbers and table are untouched. |
| A missing floor preview (404) | The map's frame says "The map of where mono depth errs could not be loaded."; its key and words stay. |
| A clip unverifiable from frame 0 (the path lost, and a travel cap hit at once, where the pipeline writes V = 0.0) | The finding reads "Verification ran out at frame 0 (0.0 s): …; no frame could be measured." D, V and the table cells say "unverifiable", and the slider's spoken value says so. There is no 0.00 for a D or a V anywhere (only times read 0.00 s), no NaN and no gold. The plan view draws the walls and no path or cursor. The real pane says why it is flat. |
| The 10 s dive at its last frame | "f240 · 10.00 s", all three panes seeked to frame 240, ArrowRight and Shift+ArrowRight stay on 240, and Play from the last frame restarts and ends there by itself. |

What the worst cases found, and the fix for each:
1. **A 60-character recording name pushed the page 199 px sideways at 390** (589 against 390). The title's crumbs were `white-space: nowrap`. A crumb is now an inline-block capped at the line: the title still breaks only between crumbs, and a crumb wider than the line wraps at its spaces.
2. **A path unverifiable from frame 0 drew `NaN`** in the plan view (`path.x[-1]`: 12 attributes, invisible on screen and silent in the console). `cursorAt` returns nothing when no frame was verified.
3. **From frame 0 the real pane said nothing about being flat.** The "From frame n, nothing here can be checked" line, which was only for n above 0, is shown from frame 0 too, without the button (there is no checked frame to go back to).
4. **With the atlas missing, the relief's note described a still that was not there.** It now says what is missing and that nothing else is.
5. **On a phone the title could start a line with "·"** (a wrapped long name). The separator ends the crumb before it, and the text still reads "A · B · C".
6. **Axe: three identical `nav` landmarks** (the plain-words bands' maps). Each is named for its chapter.
7. **At 768 an engine name broke after its hyphen in the table** ("Gen-" / "4.5"). The engine and prompt columns do not wrap.

**The items this file left for 4.6**
- **The title row reflowed by 24 px when the finding wrapped.** The finding takes one line on 28 clips at 1440, two on 5 and three on 2, so a wrap is common. The picker is now top-aligned, so it stays under the pointer: before, with `align-items: flex-end`, it moved down by a line when you picked a clip with a longer finding. The title block still grows by a line, and the stage below it moves with it. **Left, deliberately:** reserving two lines of finding on every clip costs 24 px on the 28 that need one and puts the evidence row's headers back below the fold on a first visit (896 + 24 against 900), which an e2e test holds. A test holds the picker's top on five clips with one to three lines.
- **The evidence row at 768 was three columns of 229 px.** From 761 to 1023 it is now two plus one: the plan view and the relief side by side, the numbers across the full width under them in a two-column grid. 1024 and up keep three columns (314 px at 1024). The DOM order is the desktop's, so Tab and the reading order are what is seen. The inspector's `ragged-row` at 768 no longer fires.
- **The `THREE.Clock` notice.** **Kept in the allow-list, with its reason.** `@react-three/fiber` 9.8.2 is the latest stable and builds a `THREE.Clock`; three 0.186.1 warns about it. Tried in a scratch copy: r3f 10.0.0-alpha.6 (18 days old, so old enough) silences it and the relief draws the same, but it needs the `/legacy` import to keep WebGL and is a pre-release major, and three 0.187.0 is only five days old. Taking an alpha into a public page to silence a console-only notice is the wrong trade; drop the entry when r3f 10 is stable.
- **The phone table's breadcrumb began a line with "· 5 s".** The crumb is drawn with no-break spaces before each "·" and inside "Wan 2.2", "prompt N" and "5 s", and a word joiner holds the hyphen in "Gen-4.5". A wrapped row ends a line on a "·" and never begins one with it, and never splits a unit. A Vitest holds the string (the visible text and the accessible name are unchanged).
- **Tab order.** **The picker stays first; the scrubber gets a skip link.** The design pass put the DOM in the visual order on purpose (Tab and a screen reader match what is seen), so moving the scrubber before the picker would bring back the very reorder it removed. What a keyboard user needs is not the scrubber at stop 4 but a short way to it: the page has a second skip link, "Skip to the scrubber", the second Tab stop, which focuses the slider. Without it the slider was the 13th stop on a desktop (the 15th now, behind two skip links); the picker takes three of them. A test follows the link and scrubs.
- **The reviewer's P2s.**
  - *The heat's scale against D.* The key's scale line now reads, for the default recording, "darker: no gap; lighter: a bigger gap (relative), clipped at 0.5. D 1 is a mean gap of 0.125, D 3 is 0.374." D is the mean gap over the verified pixels divided by the recording's floor, so D 1 is the floor's own gap and D 3 is three times it; where that is past the ramp's clip (Air: 0.623) it says "past the clip". It replaces the old scale line in the same space (the strip is still 81 px tall), and the figures come from `clips.json`.
  - *B, D and N.* The Prompt legend names the chosen prompt in a word ("Prompt · documentary", "· dive", "· continue") and every option carries a tooltip with all three, with the wording the engine was given. The words are the pipeline's (`pipeline/prompts.py`); `prompt_text` comes from `clips.json`. On a phone the legend is the select's label. A tooltip alone does not reach touch or keyboard, which is why the legend is visible.
  - *The D curve's use of its track.* On the default clip, 1 to 3 took 15 px of the 48. The track is now piecewise linear: 0.5 (a D under it is drawn on the bottom edge; every clip's D at frame 0 is 0.76 to 1.04) to 3 at full slope, and 3 up to the axis top at half of it. On the default clip 1 to 3 takes 22 px, and 29 px on a calm clip. **The cost:** a gold excursion is drawn about a quarter shorter (the default clip's peak of 5.37 stands 13 px above the 3 line, was 17). The D = 1 and D = 3 lines stay labelled, and gold above 3 is the same regime change the colour already marks.

**Inspector** (`inspect.mjs --app`, 1440, 768 and 390): 0 FAIL. The WARNs are the four defended above and one the earlier pass did not list: `below-fold` ("1 of 8 blocks start on the first screen" at 1440). It is not new (the build before this pass gives the same list); the stage is the biggest thing on the page and takes the first screen by design, and the evidence row's headers are on it (883 on a first visit), as an e2e test holds.

## Findings band (4 Nov, call 92)

Aaron asked for it (hub call 92). A first visit saw the clip's breadcrumb as the h1 and one clip's finding; the study's answer and its tally were nowhere on the page. The band sits between the title row and the stage. Where it departs from the sections above, this one wins.

**What it says** (`src/band/Band.tsx`)
- **The answer**, at statement size (16/600), as a paragraph and not a heading: "A dream can be checked against the real tank frame by frame, until it leaves what was measured."
- **The tally**, computed from `clips.json` when the page runs: "3 leave the tank for good · 2 spike past 3 · 25 stay under 3 · 5 can't be checked to the end".
  - It reuses the finding line's own classification. `lib/finding.ts` `findingKind` names the four forms (departs, spikes, under, unchecked), and `finding()` switches on it, so a count and a finding line cannot disagree.
  - `lib/tally.ts` counts by it, and a kind no clip has is left out. A departure that later runs out counts as a departure, because its finding line leads with the departure.
- **The two surprises**, one line each, technical voice. Both wordings in the brief were checked against THESIS.md and the data, and both over-claimed, so the wording changed and the data did not:
  - "**Dreams open the tank up:** in every clip past 3, the invented space reads farther than the real tank." The brief's "every flare reads farther" was too wide. The outlined actors on Air Wan B and Saltwater Wan B flare warm (nearer), though D leaves them out, and Freshwater, enhanced N has a nearer slab where its hatch frame stands. Measured on the heat videos over each clip's frames above 3: the pale blue ("reads farther") share grows from 0 at frame 0 to 19–59 % in all five clips past 3 (LOG "Findings band").
  - "**Only D sees a dream leave:** the Gen-4.5 clips past 3 keep V at 1.00; the rebuilt tank still covers the frame." The brief's "V stays near 1" was not true of the Wan departures: V is 0.79 and 0.67 at their departure frames and 0.54 at 5 s, where tracked actors are taken out of V. The engine and the 1.00 are computed (`steadyV`: the one engine whose clips past 3 all keep V at 0.995 or above on every measured frame, with at least one departure among them). If the data stops bearing the line out, it is left out.
- No gold (the band shows no D above 3) and no blue pencil. Square, Geist, tokens only. No entrance motion; only the counts' underline darkens on hover, under a fine pointer.

**What a count does: it filters the clip table to its clips.** It does not load the clearest example.
- Pressing a count shows only that group in the table. The table's section scrolls to the top, clear of the sticky bar, and focus moves to the line "Showing the 3 clips that leave the tank for good." Tab goes on to "Show all 35".
- Each count is a button named by its own words, then what it does ("3 leave the tank for good: show them in the clip table"), so the label is in the name.
- The stage keeps its clip, and choosing a row loads one, as before.
- **Why the filter:** it brings every clip of the group forward, one Enter away from the stage. "The clearest example" would show one clip of 25, and for "stay under 3" or "can't be checked to the end" the choice of clearest would be a judgement the data does not make.

**The fold** (the e2e test is unchanged, and the rule above still holds)
- The band alone cost 59 px. With the invite answered the headers fell to 907, against a limit of 860 so that their first line also shows; on a first visit they fell to 955, against 900.
- The first screen had no free row to give it. The title row is 1392 px wide and full: the breadcrumb and finding on the left, the picker's 835 px on the right. Beside the picker it would have taken four lines instead of two.
- So the stage pays for it, with nothing taken from the scrubber, the key strip or the media's aspect ratio:
  - the band sits 8 px under the title row and 12 px over the stage;
  - from 1024 up, the stage's block padding is its own inner gap (12) and the key strip has no extra top margin;
  - the start photograph's caption is set at 1.25, so the scrubber row is the track's own 96 px (it was 99);
  - **from 1280 up, the two panes stand over the scrubber's main column,** from the Play button's left edge to the axis labels' right edge. The frames sit straight over the curve that scrubs them, and the photograph keeps its gutter. At 1440 each pane is 608 × 342 (it was 672 × 378), and the stage is still the biggest thing on the page.
- Now the headers' bottoms are at **847** with the invite answered and **895** on a first visit. They were 848 and 896, with the same margins as before.
- Tried and dropped: a centred cap on the panes' width, driven by the viewport's height. At 1440 × 900 it gave 604 px panes, but only 2 px of margin on a first visit, through a constant tied to every height above it.

**Phone:** the band follows the title row (the picker), then the stage, at every size. The DOM is the same everywhere, so the picker stays first in Tab order (Verify pass). The answer wraps to three lines, the counts are 44 px targets two to a row, and the surprises stack.

**Checks:**
- Vitest (320, from 298):
  - `lib/tally.test.ts`: every clip's finding line has the form its kind says, on the fixture, made cases and the real 35. The tally is 3/2/25/5, and the facts file's own count agrees. `steadyV` holds on the real file.
  - `band/Band.test.tsx`.
  - `test/page.test.tsx`: the band in the page, a count filtering the table. The facts test now scans the band, with its figures from `facts.ts` `bandFigures` by its own arithmetic, and a typed count is caught.
- `e2e/band.spec.ts` at 1440 and 390, light and dark:
  - the words and counts against the served `clips.json`;
  - the band between the title row and the stage, with no gold pixel and nothing off the page;
  - two lines at 1440, 44 px targets on a phone;
  - each count by keyboard, from the picker: Tab, Enter, the table holds exactly that group, the focused line is readable once the scroll has settled, and "Show all" restores;
  - axe with the filter on.
- The whole e2e suite was green twice in a row (193 passed, 15 skipped by design). Axe found 0 violations.
- The inspector (`--app`, 1440, 768 and 390) gave 0 FAIL. Its WARNs are the four defended above (`no-poster`, `ragged-row`, `below-fold`, `numeric-align`); `colour-sprawl` no longer fires.

## Checks this direction must pass

- `inspect.mjs --app` gives 0 FAIL at 1440, 768 and 390, with the colour share defended (the stage's media are pictures, not chrome).
- Every text token reaches 4.5:1 on its surface, and non-text marks reach 3:1, both on the stage and on paper.
- Gold appears nowhere unless D > 3 (a Playwright check: scrub a clip that never passes 3 and assert no `--gold` pixels outside the media).
- The three panes seek within one frame of each other at 390 px on a throttled CPU (the task 4.6 check; held, see "Verify pass").
