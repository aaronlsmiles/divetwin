# Dive Twin: process log

The findings loop: the criteria and kill rules were frozen in `STATUS.md` before anything was generated. Each round's findings are written here before the next round starts. Nothing here is a result unless it says how it was measured. Rounds, kills and surprises are listed in the order they happened; the round table is in `STATUS.md`. This file is curated before the repo goes public.

## Round 0: the real side and the noise floor (kill rule 1)

### Start frames (task 1.2, 3 Nov)

Gate S S1 applied (three recordings swapped for same-condition takes that end empty; Air keeps a still start via `--allow-quiet air`). SAM 2.1 masks of the bottle and the hand on every frame, seeded by hand from `pipeline/seeds.json`; states, start frame and tail from `cli.py start-frames`. Contact sheet: `runs/sheets/start_frames.jpg` (each start frame beside its last frame). All five start frames show no hand and no moving bottle; Air's shows the still bottle at the far end, as accepted.

| Recording | Frames | hand / moving / quiet / empty | Start | Kind | Tail | Recipe | MAD start vs hand median |
|---|---|---|---|---|---|---|---|
| air | 352 | 89 / 0 / 263 / 0 | 351 | quiet | [291, 351], 61 | tail | 1.88 vs 14.07 |
| freshwater | 397 | 374 / 7 / 0 / 16 | 396 | empty | [386, 396], 11 | tail | 5.39 vs 8.21 |
| freshwater-basicEnhance | 391 | 357 / 8 / 4 / 22 | 390 | empty | [384, 390], 7 | masked | 6.09 vs 6.25 |
| saltwater | 342 | 330 / 3 / 0 / 9 | 341 | empty | [338, 341], 4 | masked | 2.97 vs 3.15 |
| saltwater-pellets | 455 | 367 / 14 / 2 / 72 | 454 | empty | [454, 454], 1 | masked | 1.90 vs 3.11 |

Air's quiet tail has a best-neighbour bottle IoU of at least 0.9543 on all 61 frames (margin 0.054 above the 0.9 line). The MAD cross-check is only weakly separating for freshwater-basicEnhance (6.09 vs 6.25), saltwater (2.97 vs 3.15) and pellets (1.90 vs 3.11): in murk and particles the hand frames differ little from the plate inside the hand region. It is a logged cross-check, not the decider (sub-plan A §3 item 1).

**First pass was wrong for two recordings (frame numbers).** SAM 2 lost objects it could not see and invented one it could:
- *Freshwater:* a pale glow disc at the top edge (x about 1216, y about 54, full resolution) was tracked as a moving bottle on frames 385-392 (about 2.8k half-resolution px), which broke the tail at 4 frames ([393, 396]); frames 386-396 are empty in the images. Also, the bottle and hand both dropped out on frames 60-62 and 60-63, when the bottle moved, and came back at about half the area (the smoke's two zero frames were the same loss). The 60-63 dropout is not repaired and does not touch the start frame or the tail.
- *Saltwater-pellets:* SAM 2 lost the hand and the bottle at frame 251 in the particle-filled water and reported 'empty' from 256 to 454 (a 199-frame "tail"). Looking at the frames: the hand and bottle leave at 250 (251-253 are empty), a wooden spoon stirs the pellets from 254, and the hand and bottle are back at the far end from about 270-290 to 453, faint from about 400 (visible with local contrast stretching until 452, gone at 454).

**Fix (Aaron, call 39): re-seed those two recordings only.** Freshwater: negative points on the glow at frames 386 and 389. Pellets: box prompts for the hand [1000, 60, 1320, 470] and the bottle [1095, 0, 1265, 810] (SAM 2's own extents at frame 250) at frames 300, 360 and 440. Each is in `seeds.json` with its reason. Two things the code had to learn, both test-first (`tests/test_sam_prompts.py`): later-frame box and point prompts, and a negative-only prompt applied as a refinement after a first propagation. The first refinement attempt changed nothing (identical masks): SAM 2 recomputes every non-conditioning frame on each propagation, so a click on a tracked frame is lost unless that frame is a conditioning frame (`add_all_frames_to_correct_as_cond`, set for the refinement pass only). Old masks kept in `runs/masks_r0/`.

**Result.** Freshwater tail [386, 396], 11 frames, recipe `tail` (the plan's expectation). Pellets tail [454, 454], 1 frame, recipe `masked`: the hand is in the water to 453 and the tank is empty at 454 (CLAHE view of 450-454 checked). Limit for task 1.4: the pellets masks are poor in the middle of the take (frames 412-431 flicker between hand, moving and empty, and frame 420's bottle mask is a wrong P-shaped region), and the pellets masked median leans on them. Frame 350 of that recording is a flat grey frame. Both go to the 1.4 reading.

### Vertical offset test (task 1.3a step 2b, 3 Nov)

Stereo Anywhere on matched pairs, each run twice: as published, and with the right image shifted vertically by that pair's measured `dy_px` before the half-resolution resize. First pass: one pair per recording, `dy-score` exit 4 (only 1 recording had 30 or more matches). Second pass (Aaron, call 43): two more frames per recording whose dy can be measured, taken from the candidate list as the next most SIFT matches (air 317, 199; freshwater 215, 89; freshwater-basicEnhance 264, 326; saltwater 105, 163), and the SIFT matches pooled per recording. Saltwater-pellets has no measurable dy (0 matches) and stays as published. Cost $0.123 (upper bound) of the $0.25 cap; maps in `runs/disp_dytest/`.

Per pair:

| condition | frame | dy_px | median abs diff (px) | valid published | valid shifted | SIFT n | err published (px) | err shifted (px) | gain |
|---|---|---|---|---|---|---|---|---|---|
| air | 255 | 2.60 | 1.41 | 1.000 | 1.000 | 63/63 | 0.66 | 0.65 | +2% |
| air | 317 | 2.21 | 1.09 | 1.000 | 1.000 | 59/59 | 0.96 | 0.93 | +3% |
| air | 199 | 2.50 | 1.81 | 1.000 | 1.000 | 54/54 | 1.07 | 1.07 | -0% |
| freshwater | 167 | 2.41 | 2.98 | 1.000 | 1.000 | 10/10 | 0.74 | 0.75 | -1% |
| freshwater | 215 | 2.63 | 2.52 | 1.000 | 1.000 | 6/6 | 3.63 | 2.98 | +18% |
| freshwater | 89 | 6.37 | 4.50 | 1.000 | 1.000 | 6/6 | 3.71 | 3.83 | -3% |
| freshwater-basicEnhance | 207 | 3.64 | 3.50 | 1.000 | 1.000 | 14/14 | 4.90 | 3.83 | +22% |
| freshwater-basicEnhance | 264 | 2.68 | 3.19 | 1.000 | 1.000 | 10/10 | 1.98 | 1.59 | +20% |
| freshwater-basicEnhance | 326 | 2.75 | 2.11 | 1.000 | 1.000 | 7/7 | 1.90 | 1.88 | +1% |
| saltwater | 46 | 3.90 | 2.81 | 1.000 | 1.000 | 15/15 | 0.67 | 0.57 | +15% |
| saltwater | 105 | 4.16 | 4.38 | 1.000 | 1.000 | 12/12 | 1.54 | 1.77 | -15% |
| saltwater | 163 | 2.48 | 1.75 | 1.000 | 1.000 | 10/10 | 2.05 | 1.93 | +6% |
| saltwater-pellets | 33 | not measured | 0.00 | 1.000 | 1.000 | 0/0 | n/a | n/a | n/a |

Pooled per recording (a recording counts with at least 30 pooled matches):

| condition | pairs | SIFT n used | err published (px) | err shifted (px) | gain |
|---|---|---|---|---|---|
| air | 3 | 176 | 0.93 | 0.88 | +6% |
| freshwater | 3 | 22 | 2.15 | 2.26 | -5% |
| freshwater-basicEnhance | 3 | 31 | 2.58 | 2.42 | +6% |
| saltwater | 3 | 37 | 1.35 | 1.06 | +21% |
| saltwater-pellets | 1 | 0 | n/a | n/a | n/a |

`dy-score` exit 0: the shift beat published by more than 10% on 1 of 3 measured recordings (saltwater); freshwater (22 matches) and saltwater-pellets (0) did not reach 30 pooled matches. Full run followed with the maps as published: 599 pairs, `usd_upper` 0.491, cum 0.491 of the $2.00 cap; 601 maps with the 2 smoke maps, all finite and positive.

### Units cross-check (private: delete when LOG is curated)

| condition | n | median | p25 | p75 | dy_px median |
|---|---|---|---|---|---|
| air | 129 | 1.002 | 0.999 | 1.012 | 2.46 |
| freshwater | 79 | 0.732 | 0.700 | 0.738 | 2.89 |
| freshwater-basicEnhance | 169 | 0.658 | 0.625 | 0.700 | 3.12 |
| saltwater | 131 | 0.736 | 0.728 | 0.739 | 3.64 |
| saltwater-pellets | 21 | 0.304 | 0.278 | 0.677 | not measured |

Checked only for a factor-2 error; not interpreted, not published.

### Tank maps (task 1.4)

First pass, masked recipe on basicEnhance, saltwater and pellets: failed the visual check (a hand-and-bottle ghost on basicEnhance's back wall; a black hole down the far end of saltwater and pellets; `valid` was 0.94-1.00 and caught neither). Aaron's call 45: a recording whose start is `empty` builds its map as the plain median over its empty tail, at any length. A pixel needs every frame of a tail shorter than 10 (`tail_min_obs`); a `quiet` tail still needs 10. The masked median is computed for the short tails as a cross-check only (`xcheck`: median absolute difference relative to the tail map, over pixels valid in both and outside every mask); it never feeds the map. Maps in `runs/tank/`, montage in `runs/sheets/tank_montage.jpg` (start frame, map, residual against a blur, relative IQR).

| recording | recipe | frames | valid | median rel IQR | xcheck masked med / p90 | visual check |
|---|---|---|---|---|---|---|
| air | tail (quiet) | 61 | 1.000 | 0.009 | not run | The real still bottle (accepted at Gate S) and the tap fixture; otherwise an empty tank, no hand, no smear. |
| freshwater | tail (empty) | 11 | 1.000 | 0.017 | not run | Empty tank, smooth box perspective; nothing at the far end. |
| freshwater-basicEnhance | tail (empty) | 7 | 1.000 | 0.013 | 0.018 / 0.056 | Empty tank; the first-pass ghost is gone and the far end is a clean rectangle. |
| saltwater | tail (empty) | 4 | 1.000 | 0.016 | 0.013 / 0.037 | Empty tank; the far-end hole is gone. A faint vertical streak just left of centre on the back wall, no object shape. |
| saltwater-pellets | tail (empty) | 1 | 1.000 | n/a (1 frame) | 0.038 / 0.093 | Empty tank, no hand, no bottle, no hole. A single stereo frame: the far end is mottled and the floor/back-wall join is lumpy, which fits the turbid water and the pellet debris on the floor in the start frame. |

Pellets' map is one stereo frame (frame 454), and the page should say so.

### Noise floor (task 1.5, 3 Nov)

DA3 Mono-Large on every matched real left frame (547 frames, `runs/da3/floor/`), scored against each recording's tank map after the frozen Huber scale-and-shift fit, hand and bottle masks excluded (`uv run python cli.py floor`; per-frame AbsRel and fits in `runs/floor/<name>.json`). The floor is the median per-frame AbsRel_tank.

| recording | frames | floor (median AbsRel_tank) | IQR (p25-p75) |
|---|---|---|---|
| air | 129 | 0.208 | 0.203-0.211 |
| freshwater | 81 | 0.127 | 0.123-0.131 |
| freshwater-basicEnhance | 180 | 0.125 | 0.120-0.128 |
| saltwater | 133 | 0.142 | 0.131-0.150 |
| saltwater-pellets | 24 | 0.177 | 0.150-0.199 |

**Per condition.** Saltwater-pellets is not the worst: air is (0.208, with a tight IQR). Pellets is second (0.177) and has the widest IQR of the five. Its reference is a single stereo frame with a mottled far end, so part of its floor may come from the reference rather than from DA3; the page should carry that caveat. The two freshwater recordings sit together at about 0.125, and saltwater is slightly higher at 0.142.

**Kill rule 1: holds.** 0 of 5 floors above 25 % (exit 0).

**The look.** Contact sheet `runs/sheets/floor.jpg`: one row per recording, at the frame whose AbsRel is nearest its floor (real left image | DA3 after the fit | tank disparity | |relative error| 0-50 %, excluded pixels grey).
- air (f144): concentrated at the far end. The back wall around the masked bottle and the fixture strip at the top saturate past 50 %, and the floor and walls are low (far half 0.27 against near half 0.14).
- freshwater (f213): mostly the far end around the masked hand and bottle, plus a moderate band on the left wall. Elsewhere it is low and spread out.
- freshwater-basicEnhance (f93): concentrated at the far end. The back-wall rectangle saturates around the masked bottle, and the walls and floor are low.
- saltwater (f221): two places, the far-end rectangle and a saturated strip down the left wall edge (side bands 0.28 against centre 0.09).
- saltwater-pellets (f234): concentrated at the far end and in a blocky patch left of the masked hand. That patch matches the mottled region of the single-frame tank map, not a feature in the image.

Gate F: waiting for Aaron.

## Round 0b: the self-test (kill rule 4)

### Reconstruction (task 1.6, 3 Nov)

`uv run python cli.py recon`: one grid mesh per tank map (`runs/recon/<name>.npz`), rendered from the start camera and again 100 and 200 su forward along the optical axis. The identity assert holds on all five (depth p99 relative error 5.7e-8 to 5.9e-8, colour RMSE 0.0 against the start frame). Sheet: `runs/sheets/recon.jpg` (five rows; +0, +100, +200 su).

```
air {"far_end": 947.0440063476562, "seen_0": 0.9977951388888889, "depth_rel_err_p99": 5.717680491944495e-08, "colour_rmse": 0.0, "seen_vs_valid": 0.9977951388888889, "seen_100": 0.9980110677083334, "seen_200": 0.9983875868055555}
freshwater {"far_end": 858.645751953125, "seen_0": 0.9996766493055556, "depth_rel_err_p99": 5.846405309793839e-08, "colour_rmse": 0.0, "seen_vs_valid": 0.9996766493055556, "seen_100": 1.0, "seen_200": 1.0}
freshwater-basicEnhance {"far_end": 837.2418212890625, "seen_0": 0.999755859375, "depth_rel_err_p99": 5.886417213827449e-08, "colour_rmse": 0.0, "seen_vs_valid": 0.999755859375, "seen_100": 1.0, "seen_200": 1.0}
saltwater {"far_end": 814.0655517578125, "seen_0": 0.9996853298611111, "depth_rel_err_p99": 5.8482107659617595e-08, "colour_rmse": 0.0, "seen_vs_valid": 0.9996853298611111, "seen_100": 0.9999674479166667, "seen_200": 0.9999175347222222}
saltwater-pellets {"far_end": 706.194580078125, "seen_0": 0.9994249131944445, "depth_rel_err_p99": 5.818228942215154e-08, "colour_rmse": 0.0, "seen_vs_valid": 0.9994249131944445, "seen_100": 0.9975303819444444, "seen_200": 0.9913075086805555}
```

| recording | far end (su) | seen +0 | seen +100 | seen +200 | seen_vs_valid |
|---|---|---|---|---|---|
| air | 947.0 | 0.9978 | 0.9980 | 0.9984 | 0.9978 |
| freshwater | 858.6 | 0.9997 | 1.0000 | 1.0000 | 0.9997 |
| freshwater-basicEnhance | 837.2 | 0.9998 | 1.0000 | 1.0000 | 0.9998 |
| saltwater | 814.1 | 0.9997 | 1.0000 | 0.9999 | 0.9997 |
| saltwater-pellets | 706.2 | 0.9994 | 0.9975 | 0.9913 | 0.9994 |

Every map is valid at every pixel, so seen +0 equals seen_vs_valid; the unseen share at +0 is the cut lines only.

**The look.**
- air: +0 matches the start frame. Forward, the far end, bottle and tap magnify; the bottle occludes cleanly, with a thin grey disocclusion outline and no sheet joining it to the back wall. The ratchet and strap on the near-left wall go behind the camera by +200 and leave radial orange streaks on the near wall: the map has them as part of a smooth wall (no depth step), so this is the near wall magnified, not a bridge across a jump.
- freshwater: +0 matches; the far end magnifies cleanly; no grey, no tears.
- freshwater-basicEnhance: as freshwater; clean.
- saltwater: +0 matches; clean apart from 4-5 pixel-scale flecks at the left edge of the far end (0.008 % of the frame at +200).
- saltwater-pellets: **holds to +100 su, tears by +200 su.** +0 matches. At +100 small grey flecks open in the upper-left quarter of the far end (0.25 % of the frame, 120 holes), with no flaps. At +200 they are long radial tears (0.87 %, 133 holes) with dark, feather-shaped flaps of far-end colour stretched outward over the left wall between them. The radial smear on the floor in front is the near floor magnified. Hence the cap (call 50): in pellets' dives, frames past 100 su of recovered forward travel are unverifiable (`dive.TRUSTED_TRAVEL_SU`; the clip entry records `trusted_travel_su` and `first_capped_frame`). The other four have no cap, and the self-test's 200 su path is unchanged for all five.

**Why `JUMP` does not cut the flaps.** In the mottled region the map climbs from the left wall to the far end as a ramp, not a step: along row 100, depth goes 411, 445, 479, 515 su every 20 px, about 0.4 % per pixel, so every triangle passes the 5 % cut and the ramp survives as a sheet. On the three maps measured (air, freshwater, pellets), kept faces reach the 5 % limit (max face depth ratio 0.050), but the p99 is 1.0-1.6 %.

Empty tanks show no grey at the edges as travel grows; forward travel along the axis keeps the new view inside the old one beyond the travel distance, so the walls stay covered (seen rises on four of five).

**Finding: call 49 tried and reverted (call 50).** The rule greyed a short-tail map pixel wherever the tail map and the masked median disagreed by more than 10 %, both valid. Greyed: basicEnhance 10.08 %, saltwater 4.61 %, pellets 17.05 % of the frame; air and freshwater untouched. It gave floors of 0.117 (basicEnhance, from 0.125), 0.143 (saltwater, from 0.142) and 0.116 (pellets, from 0.177); air and freshwater unchanged. It failed on two counts. First, it rested on the masked median having no value inside the masks; it has one there (it has no value on only 0 %, 3.5 % and 5.6 % of the frame), and there it is the faulty estimate. Most of the greying fell inside the mask union (basicEnhance 8.4 of 10.1 points, saltwater 4.5 of 4.6, pellets 12.4 of 17.1), in hand-and-bottle and arm shapes over back walls the tail map had clean. Second, pellets' flaps sit where the two estimates agree within 10 %: at +200 they remained, along the edge of the greyed block. A stricter reading tried in scratch (grey only outside the mask union: 1.71 %, 0.17 %, 4.61 %) left the same flaps and opened a small tear at saltwater's far end at +200. Code and tests reverted; the R4 maps and R5 floors are restored (re-run: all five floors identical, no `greyed` field), and the recon JSON above is identical to the first run.

### Self-test (task 1.7, 3 Nov)

`uv run python cli.py selftest-prep`: each tank's reconstruction rendered along the frozen path (200 su forward over 48 frames, ±3° of yaw), 49 renders per recording in `runs/selftest/<name>`. DA3 Mono-Large on the 245 renders (`modal_depth.py::selftest`, est. $0.13, billed upper bound $0.105, cap $0.50; `runs/selftest.log`). Then `uv run python cli.py selftest` (exit 0):

```
air                      tracks 0.002 (yaw max 0.02 deg)  icp(DA3) 0.945 (yaw max 7.06 deg)  icp(perfect) 0.000  null-dream D median 1.33
freshwater               tracks 0.001 (yaw max 0.01 deg)  icp(DA3) 0.489 (yaw max 3.23 deg)  icp(perfect) 0.000  null-dream D median 0.90
freshwater-basicEnhance  tracks 0.004 (yaw max 0.05 deg)  icp(DA3) 0.201 (yaw max 5.00 deg)  icp(perfect) 0.000  null-dream D median 0.71
saltwater                tracks 0.003 (yaw max 0.04 deg)  icp(DA3) 0.814 (yaw max 8.10 deg)  icp(perfect) 0.000  null-dream D median 0.68
saltwater-pellets        tracks 0.002 (yaw max 0.02 deg)  icp(DA3) 0.330 (yaw max 11.98 deg)  icp(perfect) 0.000  null-dream D median 0.68
primary path: tracks; kill rule 4 on tracks: 0 of 5 above 15 % -> holds
exit 0: kill rule 4 holds
```

Endpoint error as a share of the 200 su travel:

| recording | tracks | icp (DA3) | icp (perfect depth) | null-dream D median (max) | D_float median |
|---|---|---|---|---|---|
| air | 0.2 % | 94.5 % | 0.0 % | 1.33 (1.57) | 0.86 |
| freshwater | 0.1 % | 48.9 % | 0.0 % | 0.90 (1.05) | 0.84 |
| freshwater-basicEnhance | 0.4 % | 20.1 % | 0.0 % | 0.71 (0.96) | 0.63 |
| saltwater | 0.3 % | 81.4 % | 0.0 % | 0.68 (0.93) | 0.57 |
| saltwater-pellets | 0.2 % | 33.0 % | 0.0 % | 0.68 (0.86) | 0.57 |
| **median** | **0.2 %** | **48.9 %** | 0.0 % | | |

No estimator lost track on any recording (`lost_from` null throughout).

**The choice.** The frozen rule (`dive.choose_primary`, sub-plan A): the estimator with the lower median endpoint error wins; within 2 % of travel, depth registration (icp) keeps the job. Tracks 0.2 % against icp 48.9 %, far outside the tie band: **the primary path is tracks** (`pipeline/path_choice.json`).

**Kill rule 4 holds** on the primary: 0 of 5 recordings above 15 %. On icp it would have fired on all five.

**What the columns say.** icp on the renders' own depth recovers the path exactly, so the registration itself is sound; all of icp's error comes from DA3's depth on the renders. Its yaw errors (3-12°) exceed the ±3° the path actually turns. Tracks use no depth model and stay under 0.5 % of travel and 0.05° of yaw on every recording.

**The null-dream D** is the heat a perfectly faithful dream would show: the frozen frame-0 fit, DA3 on the renders, against the tank. Medians 0.68-1.33 (air highest; basicEnhance, saltwater and pellets lowest at about 0.7); D_float, the per-frame refit view, is lower on all five (0.57-0.86). The clips' D is read against these numbers, not against 0: a dream whose D sits near its recording's null-dream D is as faithful as this method can see.

**Pellets.** Its renders past +100 su go through the torn region (frame 48 shows a streaky floor and haze, the floor pellets smeared flat). The tracks path still recovered it to 0.2 %; icp's 33 % is the second-lowest icp error but carries the largest yaw error (12°). Pellets' dives stay capped at 100 su (call 50) whatever this says.

**The limit.** These are renders of the tank map, not dreams. The tracks estimator lifts its 2D tracks to 3D with the tank map's own depth, and the renders are made from that same map, so its geometry is exact here by construction: 0.2 % measures feature tracking and PnP on clean renders, a lower bound. On a dream the scene can drift away from the map, and the tracks path is only as good as the agreement between the dream and the tank. The self-test does not test that.

## Round 1: probes (kill rule 2)

### Setup (task 2.2, 3 Nov)

Gen-4.5 `image_to_video`, 2 s, ratio 1280:720, one clip per recording × prompt (D, B, N), first frame = the recording's start frame (`runs/start/<recording>.png`, checked by eye before paying: empty tank, no hand, no moving bottle, Air's still bottle at the far end). `uv run python runway_calls.py probes --yes`, `--max-credits 30` per clip, log `spend.jsonl`; output in `runs/probes_r1.log`, exit 0. 15 of 15 SUCCEEDED and valid (49 frames, 1280 × 720 each), 24 credits each, **360 credits ($3.60)** from the 15 `final` rows. Frame 0 of every probe matches its start image to a mean absolute difference of 0.89-1.31 grey levels (encoding loss), so the probes start on the start frame's grid.

Seeds (from `seed_for`; B and N share a seed per recording, as frozen):

| recording | D | B and N |
|---|---|---|
| air | 1809671206 | 982304778 |
| freshwater | 4049126669 | 262966149 |
| freshwater-basicEnhance | 1414675945 | 3055712936 |
| saltwater | 4181931290 | 570845773 |
| saltwater-pellets | 3879243466 | 1684437470 |

Readings: `uv run python cli.py probe-sheet` (sheet `runs/sheets/probes.jpg`, numbers `runs/probes.json`), and by eye on frames 0, 12, 24, 36 and 48 of every probe (`runs/sheets/r1/<clip>_strip.jpg`, with first, mid and last frames as PNG beside them). What the command printed:

```
air__gen45__B__probe2s                   sift  1.002 hold       ( 40 in) flow      — unmeasured change 2.03/frame
air__gen45__D__probe2s                   sift      — unmeasured (  0 in) flow      — unmeasured change 3.87/frame
air__gen45__N__probe2s                   sift      — unmeasured (  0 in) flow      — unmeasured change 3.34/frame
freshwater-basicEnhance__gen45__B__probe2s sift      — unmeasured (  0 in) flow      — unmeasured change 4.57/frame
freshwater-basicEnhance__gen45__D__probe2s sift      — unmeasured (  0 in) flow  1.778 forward    change 2.14/frame
freshwater-basicEnhance__gen45__N__probe2s sift      — unmeasured (  0 in) flow      — unmeasured change 5.96/frame
freshwater__gen45__B__probe2s            sift      — unmeasured (  0 in) flow  2.587 forward    change 2.92/frame
freshwater__gen45__D__probe2s            sift      — unmeasured (  0 in) flow  2.221 forward    change 2.62/frame
freshwater__gen45__N__probe2s            sift      — unmeasured (  0 in) flow      — unmeasured change 4.35/frame
saltwater-pellets__gen45__B__probe2s     sift      — unmeasured (  0 in) flow      — unmeasured change 5.76/frame
saltwater-pellets__gen45__D__probe2s     sift      — unmeasured (  0 in) flow      — unmeasured change 1.72/frame
saltwater-pellets__gen45__N__probe2s     sift      — unmeasured (  0 in) flow      — unmeasured change 4.42/frame
saltwater__gen45__B__probe2s             sift      — unmeasured (  0 in) flow      — unmeasured change 3.06/frame
saltwater__gen45__D__probe2s             sift      — unmeasured (  0 in) flow      — unmeasured change 1.54/frame
saltwater__gen45__N__probe2s             sift      — unmeasured (  0 in) flow      — unmeasured change 4.19/frame
prompt D: forward on 0 of 5 by SIFT (5 unmeasured), 2 of 5 by flow (3 unmeasured)   [kill rule 2, read in reverse: forward on fewer than 3 of 5 means one rewrite, Aaron's, in house wording]
prompt B: moved on 1 of 5, 3 unmeasured (forward by SIFT 0 (4 unmeasured), by flow 1 (4 unmeasured))   [kill rule 2, forward direction: 3 or more of 5 means one rewrite, Aaron's; an unmeasured probe is not a hold]
prompt N: moved on 0 of 5, 5 unmeasured (forward by SIFT 0 (5 unmeasured), by flow 0 (5 unmeasured))   [kill rule 2, forward direction: 3 or more of 5 means one rewrite, Aaron's; an unmeasured probe is not a hold]
a cross-check for the eye: Gate P reads the sheet and decides
sheet: runs/sheets/probes.jpg
```

### The fifteen probes

Motion is what the eye reads across frames 0-48. SIFT is the first-to-last similarity scale (inliers); flow is the chained zoom with its fit residual (rms px at 320 wide) and textured share; first-to-last change is in grey levels.

| recording | prompt | motion by eye | SIFT | flow | first-to-last change | invented? | notes |
|---|---|---|---|---|---|---|---|
| air | D | forward: the ratchet slides out past the left edge by frame 24, the bottle grows to about twice its height | unmeasured (0 in, 5 matches) | unmeasured (rms 0.70, texture 0.26) | 20.0 | Possibly: the tap and hose above the far end turn into a hanging ribbed tube with a black cap (frame 48) | Tank shape held; the bottle stays put. The flow fit misses the 0.6 px line by 0.10 |
| air | B | hold | 1.002 hold (40 in, shift 0.06 %) | unmeasured (rms 1.54) | 7.2 | Yes: a stream of water pours from the tap into the tank from frame 24, in front of the bottle; a rippling water surface spreads over the near floor | The only probe whose camera holds. The water is moving, which breaks the flow fit |
| air | N | forward: the ratchet leaves the frame by frame 36, the bottle grows | unmeasured (0 in) | unmeasured (rms 0.63) | 20.1 | No new object; the tap leaves the top of the frame | A dive like D's, with no camera word in the prompt. Flow misses the line by 0.03 |
| freshwater | D | forward: the far-end rectangle about doubles in width over 48 frames, with a slight side-to-side sway | unmeasured (0 in) | 2.221 forward (rms 0.55) | 24.0 | No | Tank shape held; the white tag on the back wall stays |
| freshwater | B | forward, at about D's rate | unmeasured (0 in) | 2.587 forward (rms 0.57) | 52.9 | No object; the image darkens | Moves as much as D with no camera word |
| freshwater | N | forward | unmeasured (0 in, 1 match) | unmeasured (rms 0.74) | 95.5 | No object; the whole image turns dark teal from frame 12 | Colour shift; tank shape held |
| freshwater-basicEnhance | D | forward | unmeasured (0 in) | 1.778 forward (rms 0.47) | 15.1 | Yes: two white plates and a striped label (illegible, text-like bars) appear on the back wall from frame 24 | Tank shape held |
| freshwater-basicEnhance | B | forward | unmeasured (0 in) | unmeasured (rms 1.26) | 99.6 | Yes: the image turns deep blue; a white plaque appears on the left wall; the far end becomes a room behind a frame | Colour shift; the far end changes shape |
| freshwater-basicEnhance | N | forward, fastest of the fifteen: it passes the far end by frame 36 | unmeasured (0 in, 0 matches) | unmeasured (rms 2.18) | 113.8 | Yes: two blue signs with text-like glyphs on the left wall (frame 36); beyond the far end, a dark interior with a curved hull, rails and a lit panel | The tank turns into a corridor; it leaves the measured tank |
| saltwater | D | forward; the haze clears as the far end grows | unmeasured (0 in) | unmeasured (texture 0.07) | 14.8 | Unclear: dark curved lines on the back wall sharpen out of the haze (frames 24-48). They may be the cloth behind the far window, which the start frame shows only as murk | Tank shape held. Turbid frames: flow is unmeasured by design |
| saltwater | B | forward | unmeasured (0 in) | unmeasured (rms 0.84) | 87.7 | Yes: behind the far end, a lit scaffold room with pipes and a ceiling grid from frame 12 | The image darkens. The tank walls hold; what is behind them is invented |
| saltwater | N | forward | unmeasured (0 in) | unmeasured (rms 1.13) | 119.9 | Yes: the tank turns into a dark ribbed tunnel with a bright light at its end and a fan-like round structure (frames 24-48) | The tank changes shape; colour to near-black |
| saltwater-pellets | D | forward; the haze clears and the pellet bed on the floor sharpens | unmeasured (0 in) | unmeasured (texture 0.09) | 22.4 | No; the pellets on the floor are the start frame's | Tank shape held; the turbidity drops over the clip |
| saltwater-pellets | B | forward, through the far end | unmeasured (0 in) | unmeasured (rms 1.52) | 112.4 | Yes: a black room beyond the tank, with heaps of white foam or pellets on a dark floor (frames 24-48) | Leaves the tank; colour to near-black |
| saltwater-pellets | N | forward | unmeasured (0 in) | unmeasured (rms 0.99) | 114.7 | Yes: a round hatch with a light behind it at the far end, then a pale plank or step on the floor (frame 48) | Turns into a pipe; colour darkens |

### Kill rule 2

By eye, which decides:
- **Prompt D, read in reverse:** forward on **5 of 5**, so the rule does not fire. D's probes all glide forward and keep the tank's shape.
- **Prompt B:** the camera moves on **4 of 5** (forward on freshwater, basicEnhance, saltwater and pellets; holds on air only). **The forward direction would fire (3 or more of 5).**
- **Prompt N:** the camera moves forward on **5 of 5**. **The forward direction would fire.**

The rule sends each of B and N to one rewrite in house wording. The rewrite is Aaron's, at Gate P; no prompt has been changed (`pipeline/prompts.py` is untouched). A retaken B or N breaks its seed pair, so both are retaken together (sub-plan B, S2.2 step 6).

The numbers disagree with the eye. They count D forward on 2 of 5 (by flow; 0 of 5 by SIFT), B moved on 1 of 5 and N on 0 of 5, with 3, 3 and 5 unmeasured. Read alone, they would fire the reverse rule on D and fire nothing on B or N, which is the opposite of what the frames show.

### Findings

1. **The motion cross-check does not work on Gen-4.5 at 2 s.** SIFT is unmeasured on 14 of 15 probes (0 inliers; at most 5 raw matches between the first and last frame), including air D, which has the most texture of the five. The view changes too much over 48 frames for a first-to-last match: where flow reads, the view magnifies 1.78-2.59 times over the clip, and on B and N the scene itself changes. Flow is unmeasured on 11 of 15. Two are turbid and fall under the texture line (saltwater D 0.07, pellets D 0.09). The other nine leave a fit residual of 0.63-2.18 px against the 0.6 px line, because of invented content, colour shifts and moving water. On air D and air N the residual is 0.70 and 0.63, just above the line, on what are visibly clean forward glides. Where flow does read, it reads forward with zooms of 1.78-2.59. For the finals the eye remains the only reader of camera motion; the frozen thresholds are not changed here.
2. **Gen-4.5 dives without being asked.** With no camera word in the prompt, 9 of the 10 B and N probes move the camera forward down the tank at about D's rate. The tank's own one-point perspective, with the far end centred, appears to be read as a direction of travel.
3. **N invents the most.** Four of five N probes leave or rebuild the tank inside 2 s: a corridor with signage (basicEnhance), a ribbed tunnel with a light (saltwater), a pipe with a hatch (pellets), and an all-teal darkening (freshwater). On the same seeds, B invents on four of five: behind the far end on three (the basicEnhance room, the saltwater scaffold, the pellets foam room) and the water from air's tap. It keeps the tank walls longer. The word "documentary" pushes toward dark, lit, built interiors. With five a side this is a description, not a test.
4. **D is the most faithful of the three.** The tank's shape holds on 5 of 5. Its inventions are small: labels on basicEnhance's back wall, air's tap turning into a hanging tube, and an unclear shape out of saltwater's haze. In the two turbid recordings the dream clears the water as it goes forward, so the far end gets sharper than the start frame ever shows. That is an invention of visibility, and it matters for the far-end test in the finals.
5. **Colour shifts.** Every B and N probe on the four water recordings ends darker than it starts, with first-to-last changes of 52.9-119.9 grey levels against 14.8-24.0 for D. This affects the finals' heat: the depth model will see different images, not only different geometry.
6. **The only held camera is air B,** and it is the probe with the plainest invention: water pouring from the tap into the tank. Air is the one recording with the tank in a bath under a visible tap.

Gate P: waiting for Aaron (kill rule 2 would fire on B and N by eye; D holds).

## Round 2: finals

**Done (3 Nov), in two parts.**

- **Part one:** the 15 Gen-4.5 5 s finals and the Wan smoke. Then the full Wan run refused on its projection, and the round stopped for Aaron.
- **Part two, after call 72** (Wan cap $4.50 → $5.30, Phase 2 total $5.00 → $5.80, `e047468`): the 5 long dives, the 14 Wan clips, frame mapping (2.5) and the depth smoke (S2.5b).

The hunt and Gate H wait until after Phase 3 (call 73). All 35 clips are valid and indexed, and all 35 map.

### What ran

- **Gen-4.5 finals:** `uv run python runway_calls.py finals --yes` (`--max-credits 70` each). Exit 0; log `runs/finals_r2.log`. All 15 SUCCEEDED and valid (121 frames, 1280 × 720), 60 credits each, **900 credits ($9.00)** from the 15 `final` rows.
- **Wan smoke:** `uv run python modal_wan.py --dry-run --smoke` (1 clip, estimate $0.58, cap $0.70), then `uv run modal run modal_wan.py --smoke`. Exit 0; log `runs/wan_smoke.log`.
  - The image built first time, with no pin changed.
  - The weights fetch (`2.4-wan-fetch`) cost $0.008 and took 180 s.
  - The clip (`2.4-wan-smoke`) used 354 s of GPU over 50 steps at 6.47 s a step, with 474.5 s wall, for **$0.397** against its $0.70 cap. It made `air__wan22__D__5s`: 121 frames, 1280 × 704.
  - The first tile of `runs/sheets/air__wan22__D__5s.jpg` is Air's start frame (cover crop).
- **Wan full run, dry:** `uv run python modal_wan.py --dry-run` printed:

```
14 Wan clips to make; estimate $4.16 (cap $4.50, cumulative for 2.4-wan: $0.00 already logged; Phase 2: $0.41 logged of $5.00; the card GBP 8.14 of the GBP 25 stop)
re-estimated from the smoke run: 354.20 s a clip; the 14 clips are projected at $4.80
the full run would be refused: 2.4-wan: the smoke run's own numbers project $4.80 for the remaining 14 clips, which does not fit the $4.50 task cap ($0.00 already logged) or Phase 2's $5.00 total ($0.41 logged). Nothing was started. This is Aaron's decision; no cap was raised.
```

  Exit 1. The nominal estimate assumed about 4 min a clip. The smoke measured 354 s of GPU for one clip, so the 14 clips project at **$4.80**. That's $0.30 over the task cap, and with the $0.41 already logged it passes Phase 2's $5.00 by $0.21. The real run wasn't attempted. No cap was touched. Aaron raised the cap (call 72).
- **Long dives:** `uv run python runway_calls.py long --yes` (`--max-credits 130` each). Exit 0; log `runs/long_r2.log`. 5 of 5 valid (241 frames, 1280 × 720), 120 credits each, **600 credits ($6.00)**.
- **Wan full run:**
  - `uv run python modal_wan.py --dry-run` printed: 14 clips, $4.16 nominal, re-estimated at 354.20 s a clip, projected $4.80 against the $5.30 cap. Exit 0.
  - Then `uv run modal run modal_wan.py`. Exit 0; log `runs/wan_full.log`.
  - The weights fetch cost $0.003 (cached). All 14 clips are valid (121 frames, 1280 × 704), at 343–345 s of GPU each (first call 412.5 s wall).
  - `2.4-wan` line: status ok, 4,815.6 s GPU, 5,022 s wall, **$4.197**, cap $5.30.
- **Modal cross-check** (`modal billing report --for today --show-resources`, 18:36). Billed against meter:

  | app | billed | meter (`usd_upper`) |
  |---|---|---|
  | Wan smoke | $0.399 | $0.405 (fetch + clip) |
  | Wan full | $4.152 | $4.200 (fetch + clips) |
  | Depth smoke | $0.027 | $0.061 |

  The full run finished at 18:33, so its bill may still be posting. The meter stays the upper bound, as intended.
- **Frame mapping (S2.5):**
  - `uv run python cli.py clips-index`: "35 clips; probes_index.json: 15 probes"; 35 without depth; exit 0.
  - `uv run python cli.py map` (exit 0; log `runs/map_r2.log`): **35 of 35 ok=True.**
  - All 20 Gen-4.5 clips: `fill`, ratio 0.000.
  - All 15 Wan clips: `cover`, with the same ratio for every clip of a recording:

    | recording | ratio |
    |---|---|
    | air | 0.007 |
    | freshwater-basicEnhance | 0.015–0.016 |
    | freshwater | 0.022 |
    | saltwater | 0.065 |
    | saltwater-pellets | 0.081 |

  - No mapping failure, so no retake reason.
- **Depth smoke (S2.5b):**
  - The dry run (`modal_depth.py clips --dry-run --smoke`) gave 1 clip, 121 frames, estimate $0.13, cap $0.25, exit 0.
  - `uv run modal run modal_depth.py::depth_clips --smoke` (exit 0; log `runs/depth_smoke.log`) ran `air__gen45__D__5s`.
  - `3.1-depth-smoke` line: status ok, phase 3, 97.5 s wall, **$0.061**. Its `calls` are `[3.4, 0]` (weights), `[16.5, 24]` (container start and model load: not counted), then four warm batches of `[3.2–3.3, 24]` and `[0.9, 1]`.
  - `check_depth`: ok, 121 frames, grid 1280 × 720. The clip's json says `median_window: 5`.
- **The full depth run, dry only** (`uv run python modal_depth.py clips --dry-run`, exit 0):

```
34 clips, 4714 frames; estimate $1.26 (cap $1.70, cumulative for 3.1-depth: $0.00 already logged; Phase 3: $0.06 logged of $2.00; the card GBP 20.19 of the GBP 25 stop)
re-estimated from the smoke run: 0.14 s a frame; the 4714 frames are projected at $0.94
```

  **0.14 s a frame, projected at $0.94.** That fits the $1.70 cap, and Phase 3's $2.00 with the $0.06 already logged. That is faster than the plan's 0.25 s bet and far from Phase 1's 0.91 s, so call 70's cap rise isn't needed. Not started (S3.1 waits for its own go).

### One-line readings: Gen-4.5 5 s finals and the Wan smoke

Read by eye from `runs/sheets/<clip>.jpg` (frames 0, 12, …, 120: first, middle and last plus a strip every 12 frames). Nothing quantitative yet.

| clip | camera | invented | matters for the metric |
|---|---|---|---|
| air · gen45 · D | forward, steady, ends close to the still bottle | A second ratchet clamp appears on the left wall mid-tank from f60, after the real one leaves at the left edge (a repeated object). A pale blob on the right floor at f120 | Tank shape held; light, no colour shift; near the bottle by the end, inside the measured tank |
| air · gen45 · B | forward (the probe held; this final doesn't), reaching the far end | From f60 the far end turns into a rounded tub: curved walls, a large tap and spout over a now-dark bottle; a second ratchet on the left | The tank's geometry is rebuilt in the measured region (curved walls where the real ones are flat). Strong heat expected; Air's floor is the worst (0.208) |
| air · gen45 · N | forward, to the bottle | From f72 a recessed panel wall and a second, fainter bottle to the right of the real one (f96–f120) | Tank held; ends almost filling the frame with the bottle; slight blue cast |
| air · wan22 · D (smoke) | forward, slow, with a little drift | Little: the ratchet slides out left, the far end holds; soft focus, mild flicker | Tank held; Wan 1280 × 704 is a cover crop |
| freshwater · gen45 · D | forward, steady | A small dark mark on the left wall late (f108–120) | Tank held; colour drifts from grey to teal over the clip |
| freshwater · gen45 · B | forward | White discs (bubbles) float in the water f0–48; a slotted grille appears at the base of the back wall (f96–120) | Teal shift; the grille sits at the far end, where the floor is weakest |
| freshwater · gen45 · N | forward | The floor turns into a fine mesh grating (f84–120); left wall gains streaks | Tank held; floor texture rebuilt across the near half of the frame |
| basicEnhance · gen45 · D | forward, slow | The striped label bars on the back wall return (as in the probe); a dark cable line at the far end | Tank held; bluish; text-like bars, illegible |
| basicEnhance · gen45 · B | forward | The far end opens into a dark room behind a door frame; the image darkens to near-black blue | Strong colour/darkness shift; the white tag stays as the one bright point |
| basicEnhance · gen45 · N | forward fast; leaves the tank | Through the far end into a dark room with rails (f36–60), then a ribbed circular hatch (f72–108), out into a lit machine corridor (f120) | Leaves the measured tank by about f48; a cut-like change of world |
| saltwater · gen45 · D | forward; the haze clears | The far window and its white tag sharpen out of the murk (an invention of visibility, as in the probe) | Tank held; darker far end by the end |
| saltwater · gen45 · B | forward, into the far end | Behind the far end, a dark built room with a staircase, panels and girders (f12 on), entered by f120 | The tank's walls hold while what is behind them is invented; darkens to blue-black |
| saltwater · gen45 · N | forward, into a tunnel | The tank becomes a ribbed metal duct like a turbine or fan housing, with a bright light at its end (f60–120) | Leaves and rebuilds the tank; strong colour change to brown-black |
| pellets · gen45 · D | forward, slow | The pellet bed spreads over the floor (the start frame's pellets, sharpened) | Tank held; haze stays; bluish |
| pellets · gen45 · B | forward, slow | The pellets turn into a snow-like layer on the floor; the back wall becomes a tiled or grated wall with a door frame | Blue shift; pellets' 100 su trusted-travel cap applies |
| pellets · gen45 · N | forward, into a pipe | **"Tank" read as an armoured tank:** the water tank becomes a round pipe, then a gun barrel looking out of a circular port over an open field and horizon (f60–120) | Leaves the tank completely (outdoors); word-sense switch; no text |

No clip shows legible text, a hard cut or a still image. No retake reason was found, and none was paid for.

### One-line readings: Gen-4.5 10 s long dives (prompt D)

Sheets: `runs/sheets/<clip>.jpg` with `--every 24` (frames 0, 24, …, 240).

| clip | camera | invented | matters for the metric |
|---|---|---|---|
| air · D · 10 s | forward all the way to the still bottle, which fills the frame centre by f240 | A second ratchet clamp on the left mid-tank (f144–168), as in the 5 s D; a faint second bottle to the left at f216–240 | Colour shifts to teal from f168; the tank's shape holds |
| freshwater · D · 10 s | forward, slow, with a sway; covers little distance | Little: caustic light ripples across the floor | Tank held; far end barely grows; mild teal |
| basicEnhance · D · 10 s | forward | A rippling water surface with caustic rings appears across the top of the frame (f96–192) | Tank held; teal-blue shift |
| saltwater · D · 10 s | forward; the haze clears by f120 | The far end resolves into a doorway with framed side panels (f192–240), sharper and more built than the real window | Strong colour shift to deep blue; the far end is rebuilt |
| pellets · D · 10 s | forward, slow | Sunlight caustics on the floor; the pellet bed turns orange, then patchy grey-white, and changes pattern as the camera goes | Haze clears; the 100 su trusted-travel cap applies |

The long dives stay tanks: no long D leaves the tank or adds a creature. Their inventions are a second clamp, water-surface caustics and a rebuilt far end.

### One-line readings: Wan 2.2 5 s clips

Sheets: `runs/sheets/<clip>.jpg` (every 12th frame).

| clip | camera | invented | matters for the metric |
|---|---|---|---|
| air · D | slow forward | Little; the ratchet slides out left (the smoke, above) | Tank held |
| air · B | forward | **A person** (white T-shirt, jeans) walks in from the right at f36 and away down the tank; the tank becomes a hallway with a door and a ceiling light (f60–120) | Leaves the tank; a moving person (call 69: track it, outlined, not counted in D) |
| air · N | holds, then a cut | A dark-water flash at f72–84 (cut-like), then **a military tank** slides into the frame over the near floor (f96–120) | A hard change at f72; the tank is a moving object |
| freshwater · D | holds | Nothing | Almost still: little travel to recover |
| freshwater · B | holds, slight forward | A small white blob drifts on the floor; at f120 a dark trouser leg at the right edge | Near-still; the leg is one frame on the sheet |
| freshwater · N | holds | **A military tank** drives in from the far end and grows until it fills the lower frame, barrel swinging (f12–120) | A moving object occluding most of the frame by the end |
| basicEnhance · D | slight forward and sway | Nothing new | Tank held |
| basicEnhance · B | holds | Nothing | Near-still |
| basicEnhance · N | holds | Nothing | Near-still |
| saltwater · D | holds | Nothing; the haze stays | Near-still |
| saltwater · B | holds | **People:** a red-haired woman in a blue top walks in (f12), then a man in a black dinner suit (f60–120) and a third figure in grey in front (f108–120) | Moving people, large in frame; the tank stays as backdrop |
| saltwater · N | slight forward | **A military tank** under a blue sky: the far end opens to the outdoors and the walls become a concrete yard (f24–120) | Leaves the tank; outdoors; big moving object |
| pellets · D | holds | A dark shape intrudes at the top right (f96–120); the image tints green | Near-still; colour shift |
| pellets · B | holds | **A ghostly person** in white at the right (f84–120) | Moving person, half-transparent |
| pellets · N | holds | Nothing | Near-still |

No Wan clip shows legible text. Air N has a cut-like flash; it maps (frame 0 is the start frame), so it's kept and noted, with no retake.

### B against N (five a side; described, not tested)

- **Motion:** every Gen-4.5 B and N final moves forward, so all 10 go forward.
- **What N does:** on three of five (basicEnhance, saltwater, pellets), N leaves the tank for a different world. A machine corridor through a hatch, a ribbed turbine duct, and a gun barrel looking out over a field: "documentary about a tank" read as an armoured tank. On freshwater and air, N keeps the tank and rebuilds its surfaces: a mesh floor, and a panel wall with a second bottle.
- **What B does:** B keeps the tank's walls on four of five. It invents behind the far end (saltwater's staircase room, basicEnhance's dark room, pellets' tiled wall) or in small objects (freshwater's bubbles and grille). Only air B rebuilds the tank's own shape, into a rounded tub.
- **In one line:** N swaps the world; B extends it. That is the probes' pattern, made stronger at 5 s.

**On Wan (described, not tested):**
- **B:** B brings in people on four of five: walking people on air, saltwater and pellets, and a leg at the edge on freshwater.
- **N:** N brings in a military tank on three of five (air, freshwater, saltwater).
- **Elsewhere:** basicEnhance and pellets N invent nothing.
- **The two engines read N the same way:** "a documentary about a tank" is read as an armoured tank by both, on 4 of 10 N clips in all (Gen-4.5 pellets; Wan air, freshwater, saltwater).

### Wan against Gen-4.5 (fifteen a side; described, not tested)

- **Camera:**
  - Gen-4.5 dives on all 15 finals (D, B and N).
  - Wan mostly holds still. Its D moves forward clearly only on air, and a little on basicEnhance; freshwater, saltwater and pellets D hold. B and N mostly hold too (air B and saltwater N go forward).
  - So prompt D's camera instruction is followed by Gen-4.5 and largely ignored by Wan. Path recovery will have little travel to measure on most Wan clips.
- **What gets invented:**
  - Gen-4.5 invents places: rooms, staircases, ducts, a gun-barrel view, rebuilt surfaces. It keeps the shot continuous.
  - Wan invents actors: people walking through the tank and military tanks driving in, at human or vehicle scale, which is impossible in a tabletop tank. The static scene stays the start frame's.
  - For the metric: Gen-4.5's inventions are mostly static structure, so they should flare as ordinary heat. Wan's are mostly moving objects, which call 69 takes out of D and the pose and draws outlined, as "moving: not counted in D". On Wan D clips that hold still, D should sit near the null-dream baseline.
- **Fidelity under D:** Wan's D clips are the most faithful clips of the round. They invent nothing, but mainly because they barely move.
- **Colour:** Wan keeps the start frame's colour except pellets D, which tints green. Gen-4.5 shifts to teal or blue on most water clips.
- **Cost and speed:**
  - Wan: about 344 s of A100 time per 5 s clip, $0.30 a clip on the meter ($4.60 for 15 including the smoke's cold load and fetches).
  - Gen-4.5: about 70 s per clip on Runway's side, $0.60 a clip.

### Findings

1. **The Wan projection didn't fit (a money finding).** The smoke measured 354 s of GPU per clip, against the plan's ~4 min. The guard refused, as designed, and Aaron raised the cap (call 72). The full run then cost $4.197 on the meter for 14 clips, inside the $4.80 projection.
2. **"Tank" is ambiguous to the model.** Pellets N turns the water tank into a military tank's gun barrel. That's an invention from the word, not from the image. Worth a line in the thesis: the nudge word carries meaning the start frame doesn't.
3. **Repetition as invention.** Air D and air B both add a second ratchet clamp further down the tank after the real one leaves the frame. The dream refills the frame with the object it just lost.
4. **Gen-4.5's air B moved this time.** The probe was the only held camera; at 5 s on a different seed it dives too. So "Gen-4.5 dives unprompted" now holds on 10 of 10 B and N finals.
5. **The engines split on the camera.** Gen-4.5 dives without being asked; Wan mostly holds even when asked (D moves clearly on 1 of 5). This makes path recovery an engine comparison in itself.
6. **Wan fills the tank with actors.** People on four of five B clips, military tanks on three of five N clips. Neither engine is told anything about scale, and Wan puts life-size people in a tabletop tank. These are inventions by any definition, but they move, so under call 69 they are drawn and not counted.
7. **The depth step is cheaper than feared.** The smoke runs at 0.14 s a frame with JPEG transfer (Phase 1's PNG run: 0.91 s), so the full depth run projects at $0.94.

### Gate H

Moved to after Phase 3 (call 73). A recommendation written in round 2's first part was withdrawn: whether a final's invention sits on verified pixels decides whether the hunt runs at all.

## Round 2b: the invention hunt

Not run.

## Round 3 (Phase 3): depth and tracks on the clips

- **Depth (S3.1):** `modal run modal_depth.py::depth_clips`, exit 0. 34 clips, 4,714 frames (the smoke clip `air__gen45__D__5s` was already done), 861 s wall, 165 s GPU in calls: 0.18 s a frame on wall time (the smoke's re-estimate was 0.14). Meter **$0.542** against the projected $0.94 and the $1.70 cap; billed $0.557 (the bill includes $0.049 of egress that the meter leaves out). `cli.py clips-index` then reports no clip without a depth file.
- **Seeds (`runs/clip_seeds.json`, 1280 × 704, Wan only; Gen-4.5's inventions are static places and are not tracked).** Frame is the earliest where the object is clearly and wholly in view, found on a 12-frame contact sheet:
  - `air__wan22__B__5s`, f60, person, [640, 70, 850, 700]
  - `air__wan22__N__5s`, f108, tank, [130, 55, 1130, 465] (the tank enters at f96 after the f72–84 dark flash and is cut by the frame at f96; f108 is the first frame with it whole)
  - `saltwater__wan22__B__5s`, f48, woman (red hair, blue top), [705, 95, 975, 704] (her legs run off the bottom edge)
  - `saltwater__wan22__B__5s`, f96, man (dinner suit), [600, 4, 1040, 704] (cut by the bottom edge)
  - `saltwater__wan22__B__5s`, f108, figure (the third, grey, large and never wholly in frame), [750, 0, 1280, 704]
  - `saltwater__wan22__N__5s`, f24, tank, [555, 238, 895, 520]
  - `saltwater-pellets__wan22__B__5s`, f108, person (ghostly, white), [1035, 100, 1245, 560]
  - `freshwater__wan22__N__5s`, f24, tank, [605, 348, 785, 455]
  - **Skipped:** `freshwater__wan22__B__5s` (the leg touches the right edge only at f120, never properly in frame), and all of Wan's D clips and the basicEnhance clips (nothing moving was read in them).
- **Tracks:** `modal run modal_depth.py::track_clips`, exit 0. 6 clips, 726 frames, 189 s wall, meter **$0.119** (cap $0.40), billed $0.070. Masks checked by eye on overlays of all 6 clips: each sits on its object (person and tank outlines clean; the saltwater figures cover the woman, the man and the grey figure separately; the air N tank, when it enters at f96, covers 54 % of the frame and the mask follows its hull and barrel). Masks exist only for the frames the tracker kept the object: 90 of 121 frames for air B, 51 for air N, 113 for saltwater B, 116 for saltwater N, 51 for pellets B, 121 for freshwater N.

## Round 3: path recovery and metrics (task 3.2)

A first plain read, not the findings (task 3.5 writes those), and not the review (task 3.3 tries to break the fit). CPU only, no spend.

- **Tests:** `uv run pytest -q`: 507 passed (7 min 6 s).
- **Run:** `uv run python cli.py dive` over all 35 clips. Exit 0, 7,629 s wall (2 h 7 min: about 3.5 min per 5 s clip, 7 per 10 s clip). Log `runs/dive_r3.log`; writes `runs/dive/<clip>.json` and `.npz`, and `runs/clips.json` (35 entries). No tracked file changed.
- **Sanity read:** `uv run python cli.py summary` (`runs/summary_r3.log`). **D0 is 0.76–1.04 on all 35 clips; none is outside 0.5–2**, so no mapping or fit problem to chase. The lowest are the three Wan pellets clips (0.76–0.77, the largest cover crop at ratio 0.081) and pellets' 10 s D (0.81).
- **Primary path:** tracks on every clip (`path_choice.json`). Lost on one clip only. "Forward max" is the largest recovered move along the frame-0 viewing axis; travel is the straight-line distance from frame 0 to the last held frame, so a camera that backs away shows travel with a forward max near 0.

| clip | D0 | D@5s | D@10s | V@5s | lost | wall | travel (su) | forward max (su) | path disagreement (su) | first D>3 | capped from | tracked |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| air · gen45 · B · 5s | 0.96 | 2.33 |  | 0.93 | — | — | 346 | 343 | 174 | — | — |  |
| air · gen45 · D · 5s | 0.98 | 0.60 |  | 1.00 | — | — | 395 | 395 | 73 | — | — |  |
| air · gen45 · N · 5s | 0.93 | 0.72 |  | 1.00 | — | — | 491 | 491 | 78 | — | — |  |
| basicEnhance · gen45 · B · 5s | 1.00 | 1.37 |  | 1.00 | — | — | 530 | 529 | 346 | — | — |  |
| basicEnhance · gen45 · D · 5s | 1.00 | 0.62 |  | 1.00 | — | — | 267 | 266 | 122 | — | — |  |
| basicEnhance · gen45 · N · 5s | 1.01 | 4.22 |  | 1.00 | — | — | 773 | 773 | 103 | 88 | — |  |
| freshwater · gen45 · B · 5s | 1.04 | 1.03 |  | 1.00 | — | — | 446 | 444 | 49 | — | — |  |
| freshwater · gen45 · D · 5s | 1.04 | 1.33 |  | 1.00 | — | — | 420 | 419 | 53 | — | — |  |
| freshwater · gen45 · N · 5s | 1.02 | 0.81 |  | 1.00 | — | — | 260 | 259 | 87 | — | — |  |
| pellets · gen45 · B · 5s | 0.93 | — |  | 0.00 | — | — | 462 | 447 | 201 | — | 30 |  |
| pellets · gen45 · D · 5s | 0.90 | — |  | 0.00 | — | — | 358 | 353 | 104 | — | 41 |  |
| pellets · gen45 · N · 5s | 1.03 | — |  | 0.00 | — | — | 555 | 550 | 504 | — | 20 |  |
| saltwater · gen45 · B · 5s | 0.89 | 2.70 |  | 1.00 | — | — | 495 | 490 | 108 | — | — |  |
| saltwater · gen45 · D · 5s | 0.89 | 0.76 |  | 1.00 | — | — | 357 | 357 | 36 | — | — |  |
| saltwater · gen45 · N · 5s | 0.90 | 3.88 |  | 1.00 | — | — | 706 | 703 | 149 | — | — |  |
| air · gen45 · D · 10s | 0.96 | 1.05 | 1.16 | 1.00 | — | — | 468 | 467 | 107 | — | — |  |
| basicEnhance · gen45 · D · 10s | 1.03 | 0.73 | 1.15 | 1.00 | — | — | 427 | 426 | 285 | — | — |  |
| freshwater · gen45 · D · 10s | 1.02 | 1.18 | 1.21 | 1.00 | — | — | 198 | 198 | 96 | — | — |  |
| pellets · gen45 · D · 10s | 0.81 | — | — | 0.00 | — | — | 408 | 405 | 93 | — | 62 |  |
| saltwater · gen45 · D · 10s | 0.94 | 0.71 | 1.78 | 1.00 | — | — | 504 | 501 | 129 | — | — |  |
| air · wan22 · B · 5s | 0.95 | 1.23 |  | 0.98 (after 3.3) | — | — | 525 | 523 | 166 | — | — | yes, excluded |
| air · wan22 · D · 5s | 0.95 | 0.85 |  | 1.00 | — | — | 120 | 118 | 290 | — | — |  |
| air · wan22 · N · 5s | 0.94 | — |  | — | 74 | — | 1 | 0 | 842 | — | — | yes, excluded |
| basicEnhance · wan22 · B · 5s | 0.95 | 0.71 |  | 1.00 | — | — | 64 | 63 | 88 | — | — |  |
| basicEnhance · wan22 · D · 5s | 0.93 | 0.72 |  | 1.00 | — | — | 235 | 235 | 90 | — | — |  |
| basicEnhance · wan22 · N · 5s | 0.93 | 0.83 |  | 1.00 | — | — | 47 | 47 | 110 | — | — |  |
| freshwater · wan22 · B · 5s | 1.00 | 1.24 |  | 0.23 | — | — | 232 | 0 | 296 | — | — |  |
| freshwater · wan22 · D · 5s | 1.01 | 0.87 |  | 0.92 | — | — | 5 | 2 | 228 | — | — |  |
| freshwater · wan22 · N · 5s | 1.00 | 2.27 |  | 0.65 (after 3.3) | — | — | 24 | 0 | 413 | — | — | yes, excluded |
| pellets · wan22 · B · 5s | 0.77 | 0.88 |  | 0.92 (after 3.3) | — | — | 2 | 2 | 171 | — | — | yes, excluded |
| pellets · wan22 · D · 5s | 0.76 | 1.16 |  | 0.41 | — | — | 121 | 0 | 319 | — | — |  |
| pellets · wan22 · N · 5s | 0.77 | 0.63 |  | 0.90 | — | — | 13 | 0 | 280 | — | — |  |
| saltwater · wan22 · B · 5s | 0.92 | 3.89 |  | 0.54 (after 3.3) | — | — | 207 | 201 | 494 | 102 | — | yes, excluded |
| saltwater · wan22 · D · 5s | 0.94 | 0.88 |  | 0.93 | — | — | 10 | 1 | 207 | — | — |  |
| saltwater · wan22 · N · 5s | 0.94 | 3.76 |  | 0.54 (after 3.3) | — | — | 424 | 423 | 129 | 97 | — | yes, excluded |

"basicEnhance" is freshwater-basicEnhance and "pellets" is saltwater-pellets. D@10s applies to the long dives only. V@5s on the five tracked clips marked "(after 3.3)" is the value after the review's fix (V now leaves tracked pixels out, call 63); air Wan N, the sixth tracked clip, is lost before 5 s. Its V at f70–73 moved from 0.98–0.99 to 0.67–0.18. For pellets' 10 s dive it is empty, because frames past the cap carry no D.

**Tracked pixels (call 69): out of D, but inside V.** I re-ran `dive.frame_products` with the stored primary pose on the three frames where the track is largest, in each of the six tracked clips (18 frames; a scratch script, no code changed):
- The verified set never touches a tracked pixel (overlap 0 on all 18).
- The stored `abs_rel` matches the recomputed value exactly, so tracked pixels are kept out of D as call 69 says.
- The frame-0 fit and both path estimators also take the track out (`run_clip`, `track_path`, `_icp_path`). Only freshwater Wan N has any track at frame 0 (0.1 % of the frame).
- **The reported V does count tracked pixels.** `run_clip` sets `V = verified_share(render.seen)`, the share of the frame the re-rendered tank covers, so it includes moving pixels. Call 63 says tracked pixels are "taken out of the verified set". On these frames, V without the track would be:

| clip | V reported | V without the track |
|---|---|---|
| saltwater Wan B, f110–112 | 0.9999 | 0.45 |
| saltwater Wan N, f118–120 | 0.9999 | 0.54 |
| air Wan B, f39–41 | 0.997 | 0.72–0.74 |
| air Wan N, f71–73 | 0.99 | 0.18–0.42 |
| freshwater Wan N, f117–120 | 0.79 | 0.65 |
| pellets Wan B, f94–98 | 0.99 | 0.90 |

  For task 3.3 to rule on: is it a definition (V as tank coverage) or a fix (V on the verified set)? The page's "grey is where no real camera ever looked" fits the first reading; the "verified share" name fits the second.

**Flags (for task 3.3; nothing fixed here):**
1. **V near 1 on clips that plainly leave the tank.**
   - basicEnhance Gen-4.5 N (machine corridor by f120): V 1.00 at 5 s.
   - saltwater Gen-4.5 N (ribbed duct): V 1.00.
   - air Wan B (hallway): V 1.00.
   - saltwater Wan N (outdoor yard): V 1.00.

   V measures whether the re-rendered tank covers the frame from the recovered camera, not whether the dream still shows a tank. D carries the departure on three of the four: 4.22 (first D>3 at f88), 3.88 and 3.76 (first D>3 at f97). Air Wan B's D peaks at 3.14 at f40 (while the person is large in frame) and ends at 1.23, never holding above 3 for 12 frames.
2. **The wall test fires on no clip.** The largest forward move is 773 su (basicEnhance Gen-4.5 N), against its measured far end of 837 su. By eye that clip is through the far end by about f48, where the recovered path is at 433 su. Tracks lift features with the tank map's own depth, so once the dream's world stops being the tank, its path is still scaled as if it were. That's the self-test's stated limit, now visible on a real clip.
3. **Most Gen-4.5 paths go past the self-test's 200 su.** Travel is 198–773 su; only freshwater's 10 s dive stays inside it. Kill rule 4 validated 200 su.
4. **Wan clips read as still by eye, but with travel:**
   - **freshwater Wan B:** 232 su, all of it **backwards** (forward max 0; the camera ends at z −231). V falls steadily from 1.00 to 0.23 as the recovered camera backs out of the reconstructed tank. **The sheet supports it.** Round 2's reading ("holds, slight forward") was wrong: on `runs/sheets/freshwater__wan22__B__5s.jpg` the far window shrinks steadily from f0 to f120, a slow pull-back. So V's fall here is the method working.
   - **pellets Wan D:** 121 su, also backwards, with 2.5° of yaw; V falls to 0.41. The sheet is hazy and greens over, and a pull-back is not clear by eye either way. Check it in 3.3.
   - **saltwater Wan B:** 201 su forward and 4.4° of yaw, while the sheet's tank background looks held. People cover up to 55 % of the frame there, so tracks run on 126–235 inliers. D reaches 3.89 (first D>3 at f102). This is the likeliest invented motion, and D on this clip may reflect a wrong path rather than a lie in the tank. Check it in 3.3.
   - **basicEnhance Wan D:** 235 su forward against a reading of "slight forward and sway". Possible, but large for Wan.
   - The other Wan "holds" clips recover 2–64 su, consistent with their readings.
5. **Path held after `lost`.** Only air Wan N is lost: tracks at f74 (in the dark flash, f72–84), ICP at f77. The path moves 0.0 su after f74, and D and abs_rel are NaN from f74 on. The 0.0 su is from the path stored to 2 dp. Lost means lost here.
6. **Air Wan N's track starts at f70, inside the flash, not at the tank's entry (f96).** SAM 2's propagation put the mask on the flash frames (58–82 % of the frame at f71–73). Tracks are lost at f74, so this changes nothing in D. But the "moving" outline in the assets would sit on the flash.
7. **Path disagreement is large everywhere.**
   - Gen-4.5: 36–504 su, 10–91 % of travel.
   - Wan: 88–842 su; as a share it explodes on still clips, where travel is near 0.
   - 31 of 35 clips pass task 3.3's 15 % line (all but freshwater Gen-4.5 B at 11 %, freshwater Gen-4.5 D at 13 %, saltwater Gen-4.5 D at 10 % and basicEnhance Gen-4.5 N at 13 %).
   - Expected from the self-test (ICP's median endpoint error 48.9 %), but 3.3's step 4 now covers nearly every clip. On still clips the share of travel is not a useful scale; su is.
   - Two non-primary ICP runs lose track: basicEnhance Gen-4.5 N at f69, pellets Gen-4.5 N at f111.
8. **Pellets' Gen-4.5 clips have no D at 5 s.** The 100 su cap (call 50) fires at f20–62 on all four, so V is 0 from there. Pellets N's gun barrel (f60 on) and every pellets Gen-4.5 frame past about 1–2.5 s are unverifiable by design. The Wan pellets clips never reach the cap (forward max ≤ 2 su).
9. **Long dives: none is flat while the picture changes much.**
   - air: D peaks at 2.46 at f196, as the second clamp appears and the colour turns teal, then 1.16 at 10 s.
   - saltwater: from a low of 0.52 (f81) to 1.80 at the end, as the far end is rebuilt (f192 on).
   - freshwater: 0.92–1.29 throughout, over only 198 su, where the picture adds only caustic ripples.
   - basicEnhance: D stays at 0.64–0.89 through f96–192 (low 0.64 at f190) while a rippling water surface spreads across the top of the frame, then rises to 1.15. Mono depth reads that texture invention as flat.
10. **D at or below 1 on dives that hold the tank:**
   - Gen-4.5 D 5 s ends at 0.60–1.33.
   - Wan "holds" clips sit at 0.63–0.88, inside or under the null-dream D medians (0.68–1.33).

   As expected for faithful clips. D below D0 late in a dive (air D 0.60, basicEnhance D 0.62) happens as the far end fills the frame.

### Review (task 3.3)

A fresh Opus 5.5 · high subagent, 3 Nov. It read master §7, sub-plan A §3, calls 35, 47, 50, 63, 69 and 73–75, the pipeline code and tests, `runs/clips.json` and `runs/dive/`, and ran sub-plan A's task P3 steps 1–4 before reading the task 3.2 section above. CPU only, no Modal or Runway call. Scratch scripts sit in the session scratchpad and are not committed.

**Step 1, D(0) ≈ 1: passes.** D0 is 0.76–1.04 on all 35 clips. None is outside 0.5–2, so no box or fit had to be redone by hand. The frozen fits are consistent per recording: s is positive everywhere (178–276), t is 28–106, and 84–100 % of the fit mask lies within Tukey's c. Frozen and floating D agree at frame 0 on every clip, to ±0.01.

**Step 2, a still clip: passes.** The smallest travel is air Wan N: 1.5 su, |yaw| ≤ 0.45°, V ≥ 0.98 until the path is lost at f74. The smallest prompt-B clip is pellets Wan B: 2.2 su, |yaw| ≤ 0.73°, V ≥ 0.977 before fix 1 and ≥ 0.90 after it (a tracked person from f70). Neither invents motion. After fix 1, air Wan N's V falls to 0.67–0.18 at f70–73: the tracked dark mass of flag 6 covers the frame, not a failure of the path.

**Step 3, lost means lost: passes.** Only air Wan N's primary path is lost (tracks, f74). From f74 on, `D`, `abs_rel`, `D_float` and `verified` are null on all 47 frames, `R` and `C` are exactly constant (`np.allclose`), and `wall_frame` and `first_D3` are None. ICP, which is not the primary, is lost on three clips (air Wan N f77, basicEnhance Gen-4.5 N f69, pellets Gen-4.5 N f111). On the last two its stored `C_icp` keeps moving after the loss. Nothing draws `C_icp`, `path_disagreement` is read at the last frame both paths hold, and the assets null the per-frame `icp` diagnostics only from the *primary's* unverifiable frame. So the page can show ICP fitness past ICP's own loss. Harmless today, noted for 3.4.

**Step 4, the two estimators: the images support tracks over ICP on 34 of 35 clips, and the 35th is past its cap.** 31 clips have `path_disagreement` above 15 % of travel. Reading 31 sheets by eye cannot tell 100 su apart, so a witness that neither estimator uses: on every 12th frame, the tank is rendered from the tracks pose, from the ICP pose and from the start pose (a camera that never moved), and each render's gradient image is correlated with the generated frame's, on pixels all three renders see and no track covers. Means over frames 12 on:

| clip | tracks | ICP | still |
|---|---|---|---|
| air · gen45 · B · 5s | 0.46 | 0.13 | 0.16 |
| air · gen45 · D · 10s | 0.33 | 0.10 | 0.11 |
| air · gen45 · D · 5s | 0.39 | 0.10 | 0.13 |
| air · gen45 · N · 5s | 0.24 | 0.09 | 0.11 |
| basicEnhance · gen45 · B · 5s | 0.39 | 0.10 | 0.13 |
| basicEnhance · gen45 · D · 10s | 0.36 | 0.13 | 0.15 |
| basicEnhance · gen45 · D · 5s | 0.59 | 0.13 | 0.20 |
| basicEnhance · gen45 · N · 5s | 0.20 | 0.08 | 0.13 |
| freshwater · gen45 · B · 5s | 0.54 | 0.11 | 0.15 |
| freshwater · gen45 · D · 10s | 0.54 | 0.10 | 0.17 |
| freshwater · gen45 · D · 5s | 0.56 | 0.08 | 0.12 |
| freshwater · gen45 · N · 5s | 0.51 | 0.11 | 0.12 |
| pellets · gen45 · B · 5s | 0.14 | 0.05 | 0.14 |
| pellets · gen45 · D · 10s | 0.19 | 0.09 | 0.15 |
| pellets · gen45 · D · 5s | 0.21 | 0.08 | 0.10 |
| pellets · gen45 · N · 5s | 0.07 | 0.11 | 0.11 |
| saltwater · gen45 · B · 5s | 0.19 | 0.08 | 0.10 |
| saltwater · gen45 · D · 10s | 0.26 | 0.06 | 0.09 |
| saltwater · gen45 · D · 5s | 0.31 | 0.08 | 0.09 |
| saltwater · gen45 · N · 5s | 0.10 | 0.03 | 0.05 |
| air · wan22 · B · 5s | 0.22 | 0.07 | 0.14 |
| air · wan22 · D · 5s | 0.53 | 0.11 | 0.30 |
| air · wan22 · N · 5s | 0.52 | 0.08 | 0.34 |
| basicEnhance · wan22 · B · 5s | 0.74 | 0.17 | 0.30 |
| basicEnhance · wan22 · D · 5s | 0.56 | 0.12 | 0.15 |
| basicEnhance · wan22 · N · 5s | 0.65 | 0.18 | 0.30 |
| freshwater · wan22 · B · 5s | 0.58 | 0.13 | 0.24 |
| freshwater · wan22 · D · 5s | 0.61 | 0.16 | 0.24 |
| freshwater · wan22 · N · 5s | 0.49 | 0.12 | 0.25 |
| pellets · wan22 · B · 5s | 0.56 | 0.16 | 0.47 |
| pellets · wan22 · D · 5s | 0.26 | 0.06 | 0.23 |
| pellets · wan22 · N · 5s | 0.36 | 0.08 | 0.45 |
| saltwater · wan22 · B · 5s | 0.12 | 0.02 | 0.06 |
| saltwater · wan22 · D · 5s | 0.41 | 0.08 | 0.35 |
| saltwater · wan22 · N · 5s | 0.10 | 0.06 | 0.05 |

- **Tracks beat ICP on 34 of 35 clips.** The exception is pellets Gen-4.5 N, which is past its 100 su cap from f20, so unverifiable anyway.
- **ICP's renders match worse than a camera that never moved, on 34 of 35 clips** (the exception is saltwater Wan N). ICP sits 89–453 su forward by f12 (median 172), on still clips too (the same DA3 shape bias the self-test measured: 48.9 % endpoint error, 3–12° of false yaw). So `path_disagreement` measures ICP's failure, not an uncertainty band on the tracks path.
- **Tracks beat the still camera on 33 of 35.** The two exceptions are pellets Gen-4.5 N, which is past its 100 su cap from f20 (so unverifiable anyway), and pellets Wan N, a near-still clip (13 su) whose small lateral drift costs it against the still render (0.36 against 0.45). That drift is inside step 2's "under about 20 su".
- By eye, the generated frame beside the tank rendered from the tracks pose and from the start pose agrees with the witness on the two clips where it matters most: saltwater Wan B at f60 and basicEnhance Gen-4.5 N at f48 (Q2 and Q3 below). An image-only zoom (dense flow about the centre, no tank, no path) also agrees in direction: basicEnhance Wan D zooms in 1.39× (tracks 235 su forward), freshwater Wan B zooms out to 0.76× (tracks 231 su back), and pellets Wan D zooms out slightly to 0.985× (tracks 119 su back; weak, as pellets' haze allows).

**The 3.2 flags, ruled on.**

Each ruled as a bug (code departs from §7, sub-plan A or a call), a definition the docs settle, or a limit to state.

1. **V on tracked clips counts tracked pixels: a bug, fixed.** §7 reads D "on S_k only" and V = |S_k| / frame area, so V and D share one set of pixels. Sub-plan A §3 item 5 takes the track out of that set, and call 63 says "tracked moving pixels are taken out of the verified set" (call 69 keeps that and only draws heat over them, outlined, in the assets). `frame_products` already builds that set (`verified = seen & ~moving`) and reads D on it, but `run_clip` took V from `render.seen`. Now V reads `verified` (`c93c2b2`). DA3 depth is finite on every pixel of all 35 clips, so V changes only where a track exists: the six tracked Wan clips, re-run. The page's "grey is where no real camera ever looked" still describes the hatch; a tracked object is outlined, not grey, and the V number now says it is not counted.
2. **The wall test fires on no clip: a limit to state, not a bug.** The test is the one §3 item 7 and call 28 froze: the recovered camera's forward travel against the far end as measured (the 80th percentile of tank depth in the central window), while the path holds. The code does exactly that. On basicEnhance Gen-4.5 N the far end (837 su) is the back of the dark recess. The white walls end at about 560–690 su on the centre row. At f48 the generated frame and the tank rendered from the tracks pose (433 su) both show the mouth of the recess with its rails and label, so the camera there is at the recess, not through the far end. It passes the back wall into an invented tunnel at about f72–84. By then every reseeded track is lifted from the tank render, so PnP keeps the camera in front of the tank's own surfaces: the path creeps to 773 su and cannot cross 837. That is the self-test's stated limit (call 52; sub-plan A §3 item 3): the tracks path is measured against the tank, so it cannot follow a dream out of it. D does register the departure: it rises from f60 and holds above 3 from f88 (`first_D3` = 88). So does flag 1 of 3.2, where V stays near 1 on clips that leave the tank: V is tank coverage seen from a path anchored to the tank, as §7 defines it. Proposal P1.
3. **Paths beyond 200 su: a limit, measured here.** Kill rule 4 validated 200 su. A review diagnostic, not the frozen self-test and changing nothing: each tank rendered along a 121-frame path to 60 % and 80 % of its far end (±3° yaw), tracks only (no depth model, CPU). Endpoint error as a share of travel:

| tank | 60 % of far end | 80 % of far end |
|---|---|---|
| air (far end 947 su) | 0.1 % at 568 su | 0.1 % at 758 su |
| freshwater (859) | 0.3 % at 515 su | 0.4 % at 687 su |
| basicEnhance (837) | 0.3 % at 502 su | 0.5 % at 670 su (yaw error up to 1.2°) |
| saltwater (814) | lost at f105 (about 427 su); drift ≤ 0.6 % before | lost at f81 (about 440 su); drift ≤ 0.3 % before |
| pellets (706; capped at 100 su anyway) | lost at f119 (about 420 su) | lost at f86 (about 405 su) |

In saltwater and pellets, reseeding works (400 new corners a frame, all lifted to 3D), but almost none survive the next frame's tracking checks (status and the 1 px forward-backward test). Near the far end the render is one stereo frame's colours stretched over the wall, and its corners don't track. So the estimator declares the path lost rather than drifting, as designed. The limit to state: in saltwater, beyond about 430 su, a path is held by the dream's own texture, which renders can't test. Three saltwater clips go past it (Gen-4.5 B 495 su, D 10 s 504 su, N 706 su), and Wan N (423 su) reaches it. So on clean renders of three tanks the tracks estimator holds to 80 % of the far end, well past 200 su. What it cannot do is follow a dream whose world stops being the tank (flag 2).
4. **Wan clips that read as still, with travel: the paths are real.**
   - **saltwater Wan B (Q3), 201 su forward and 4.4° of yaw: real, not invented by the people.** (a) The tracked pixels are out of the pose on every frame: with `cv2.solvePnPRansac` instrumented over the clip's 120 PnP calls, 0 of 30,555 correspondences sit on their frame's mask; 5.8 % lie within 10 px of an outline. (b) Dilating the masks by 10, 30 and 60 px leaves the path at 200, 200 and 205 su (yaw 4.6°, 5.0°, 7.3°: the widest dilation removes much of the background). (c) The motion starts before the people matter: 24 su by f12, when tracks cover 3.5 % of the frame, then linear at about 1.7 su a frame. (d) At f60 the floor stripe, the wall marks and the far end in the generated frame sit where the tank rendered from the tracks pose (96 su) puts them, not where the start pose does; the witness favours tracks on every sampled frame to f96 (narrowly at f96: 0.051 against 0.049), and at f108–120, with people over half the frame, neither render matches. So Wan pushes in slowly while the people walk on, and the background only *looks* held because the push is slow. D's sustained run from f102 is read against a right path.
   - **basicEnhance Wan D, 235 su: supported** (image-only zoom 1.39×; witness 0.48–0.68 for tracks against 0.05–0.23 for a still camera).
   - **pellets Wan D, 119 su back: weakly supported** (zoom 0.985×; witness 0.17–0.46 for tracks against 0.13–0.40 still). Pellets' haze leaves little to read.
   - **freshwater Wan B, 231 su back:** as 3.2 found (zoom 0.76×; witness 0.58 against 0.24).
5. **Path held after `lost`: confirmed** (step 3).
6. **air Wan N's track from f70 (Q4): a limit to state, not a bug.** At f70 a dark mass sweeps in from the top and fills 74–98 % of the frame at f72–84. It resolves into the military tank by f90–96, so SAM 2 followed one object back to its entry. Re-tracking the clip with no mask at all loses the path at f72, earlier than the stored f74, so the darkness ends the path, not the mask. The mask therefore touches only f70–73. After fix 1, V there reads 0.67, 0.42, 0.26 and 0.18 (it was 0.98–0.99). In the assets the outline from f70 sits on the dark mass, and from f74 everything is hatched. Re-seeding at f96 would be a paid SAM 2 call, and trimming the mask by hand would put an eye judgement in the data; neither is warranted for four frames. Proposal P3.
7. **Path disagreement (Q5): the 15 % line is the docs' check, but a share of travel is the wrong scale on near-still clips.** Sub-plan A task P3 step 4 sets the line. On near-still clips travel is 1.5–13 su, so ICP's wander alone gives 1,700–57,000 %. Step 4's witness shows the disagreement is almost all ICP's error, on every clip. Proposal P2.
8. **Pellets' Gen-4.5 clips have no D at 5 s: the definition (call 50).** Confirmed: V is 0 and D null from `first_capped_frame` on; no D or V is reported past the cap. Note for 3.4: `runs/clips.json`'s `wall_frame` in the dive entry is computed over the whole held path, cap included; the assets recompute it from trusted frames (pellets' far end is 706 su against a 100 su cap, so it can't fire there).
9. **Long dives and 10. D at or below 1 on faithful dives:** read and agreed; nothing to fix. They are findings for 3.5.

**Fixes.**

- **V on the verified set** (flag 1; call 63; `c93c2b2`). Test first: `tests/test_dive.py::test_tracked_moving_pixels_are_not_verified` plants a 12 % track from frame 10 and requires V to drop by that share from there on, and stay the same before. It failed on the old code (V 1.0 against an expected 0.88), then passed. One line in `dive.run_clip`: `V[i] = verified_share(fp["verified"])`. Suite: 508 passed (7 min 14 s; 507 before, plus the new test). Re-run: `cli.py dive` on the six tracked Wan clips only (`runs/dive_r3_review.log`, about 16 min, exit 0). D, the paths, `first_D3`, `lost_from` and `wall_frame` are unchanged on all six; V moved:

| clip | V@1s | V@2.5s | V@5s | lowest V (frame) |
|---|---|---|---|---|
| air · wan22 · B · 5s | 1.00 → 1.00 | 1.00 → 0.93 | 1.00 → 0.98 | 1.00 → 0.72 (f40) |
| air · wan22 · N · 5s | 0.98 → 0.98 | 0.98 → 0.98 | — (lost at f74) | 0.98 → 0.18 (f73) |
| freshwater · wan22 · N · 5s | 0.99 → 0.98 | 0.90 → 0.86 | 0.79 → 0.65 | 0.79 → 0.65 (f120) |
| pellets · wan22 · B · 5s | 0.99 → 0.99 | 1.00 → 1.00 | 0.98 → 0.92 | 0.98 → 0.90 (f94) |
| saltwater · wan22 · B · 5s | 1.00 → 0.78 | 1.00 → 0.80 | 1.00 → 0.54 | 1.00 → 0.45 (f112) |
| saltwater · wan22 · N · 5s | 1.00 → 0.94 | 1.00 → 0.85 | 1.00 → 0.54 | 1.00 → 0.54 (f120) |

These match 3.2's scratch estimates of V without the track.

No other departure from §7, sub-plan A or a call was found.

**Proposals for Aaron (none applied).** None blocks the assets: each is wording, or a reading added after the numbers.

- **P1. The wall test and clips that leave the tank (flag 2, Q2).** (a) Keep the frozen test, and say on the page and in the thesis: "The dream's path is measured against the real tank, so it can't follow a dream out through the far end. The far-end test only fires while the dream stays inside; a dream that leaves shows as heat that stays above 3× the floor instead." Report `first_D3` as the departure frame. (b) Add a "left the tank" reading: the first frame from which the tank rendered from the path stops explaining the generated frame for 12 frames (this review's render match falling to the still camera's level). That is a new metric, chosen after seeing the data. (c) Move the far end to a nearer percentile, so that reaching the recess mouth counts: that moves a frozen number after the data. **Recommend (a).** It uses only frozen numbers, and it is honest about what a tank-anchored path can't see. D already carries the departure on three of the four clips 3.2 names as leaving: basicEnhance Gen-4.5 N and saltwater Wan N hold above 3 from f88 and f97, and saltwater Gen-4.5 N crosses 3 at f116, too late in the clip for a 12-frame run. Air Wan B's hallway never holds above 3.
- **P2. How to read the path disagreement (flag 7, Q5).** Report it in su, and when it's given as a share, divide by max(travel, 200 su), the self-test's frozen travel, so near-still clips don't explode. On the page it's "how far a second estimator, which uses only the depth model, lands from the primary path", with this review's finding that the images favour the primary on 34 of 35 clips. It is never an error bar. **Recommend adopting** (wording plus one line of `cli.summary`; no metric changes).
- **P3. air Wan N's mask from f70 (flag 6, Q4).** Leave the mask as SAM 2 made it, and add a note on the page and in `clips.json`'s provenance that the outline from f70 follows a dark mass that resolves into the tank by f90. Alternatives: trim the mask to f90 by hand (an eye judgement in the data), or re-seed SAM 2 at f96 (paid, and it changes four frames). **Recommend leaving it.**
- **Note for 3.4 (no proposal needed).** The assets null the per-frame `icp` diagnostics from the *primary's* unverifiable frame. ICP's own fitness and scale after its own loss (basicEnhance Gen-4.5 N from f69, pellets Gen-4.5 N from f111) would still be listed. Nothing draws ICP's path, so this changes no picture. If the page ever plots ICP, null it from `icp.lost_from` too.

## Assets (task 3.4)

CPU only, no spend, nothing uploaded. `cli.py assets --recordings-only` (exit 0, 9.5 s), then `cli.py assets` (exit 0; log `runs/assets_r3.log`): 35 clips, 5 recordings, 5 clips with an unverifiable tail (air Wan N from f74; pellets Gen-4.5 B f30, D 10s f62, D 5s f41, N f20). Manifest: 306 files, 252.4 MB (`runs/assets`, 251 MB on disk); 35 `gen.mp4`, all `original`, bytes re-hashed and equal to `source_sha256` (35 of 35); no `unreferenced` warning. `MEDIA.md` is under the ignored `runs/`, so it is not committed.

Looked at: the five `floor_preview.jpg` (the error sits on the far-end rectangle in each; pellets' is a large bright far end with a blocky, ragged left edge, not examined further); one poster and one heat poster per recording (Gen-4.5 B 5 s); pellets D 10s last frame: `real.mp4` flat grey, `heat.mp4` the 45 degree hatch; `saltwater__wan22__B__5s` heat at f96: the two people carry heat in tan with a 2 px white outline; `freshwater-basicEnhance__gen45__N__5s` heat at f96: it flares (tan and orange across the left wall, ring artefacts at the far end). Note: pellets B's heat poster is wholly hatch (unverifiable from f30), as designed.

## Round 3: findings

Task 3.5, 3 Nov (Opus 5.5 subagent). Analysis only: no paid call, no code change. Every number below comes from the final `runs/assets/clips.json` (the 3.4 build, after 3.3's fix), printed by a scratch script, none typed by hand. Map readings come from the heat videos, every 24th frame with the generated frame above its heat (`runs/assets/clips/<clip>/heat.mp4` and `gen.mp4`; sheets in the session scratchpad, not committed). The heat's ramp runs from dark (small residual) to pale (|r| at or above 0.5); tan means the dream reads nearer than the real tank, blue means farther, hatch means unverified, and a white outline marks a tracked moving object.

### D and V at 5 s (D / V)

| recording | Gen-4.5 B | Gen-4.5 D | Gen-4.5 N | Wan B | Wan D | Wan N |
|---|---|---|---|---|---|---|
| air | 2.33 / 0.93 | 0.60 / 1.00 | 0.72 / 1.00 | 1.23 / 0.98 | 0.85 / 1.00 | — / — ˡ |
| freshwater | 1.03 / 1.00 | 1.33 / 1.00 | 0.81 / 1.00 | 1.24 / 0.23 | 0.87 / 0.92 | 2.27 / 0.65 |
| basicEnhance | 1.37 / 1.00 | 0.62 / 1.00 | 4.22 / 1.00 | 0.71 / 1.00 | 0.72 / 1.00 | 0.83 / 1.00 |
| saltwater | 2.70 / 1.00 | 0.76 / 1.00 | 3.88 / 1.00 | 3.89 / 0.54 | 0.88 / 0.93 | 3.76 / 0.54 |
| pellets | — / 0.00 ᶜ | — / 0.00 ᶜ | — / 0.00 ᶜ | 0.88 / 0.92 | 1.16 / 0.41 | 0.63 / 0.90 |

ᶜ Pellets' 100 su travel cap (call 50): the Gen-4.5 clips pass it at f30 (B), f41 (D) and f20 (N), so there is no D at 5 s, and V reads 0.00 by definition (unverifiable, not "nothing seen"). ˡ Air Wan N's path is lost at f74 in the dark flash, so it has no value at 5 s; at 2.5 s it reads D 1.27, V 0.98.

**Long dives (Gen-4.5 D, 10 s).** Four of the five have values; pellets passes its cap at f62 (D at 2.5 s is 0.78 with V 1.00, then nothing).

| long dive (Gen-4.5 D, 10 s) | D@5s | V@5s | D@10s | V@10s | peak D (frame) |
|---|---|---|---|---|---|
| air | 1.05 | 1.00 | 1.16 | 1.00 | 2.46 (f196) |
| freshwater | 1.18 | 1.00 | 1.21 | 1.00 | 1.29 (f89) |
| basicEnhance | 0.73 | 1.00 | 1.15 | 1.00 | 1.15 (f240) |
| saltwater | 0.71 | 1.00 | 1.78 | 1.00 | 1.80 (f238) |
| pellets | — ᶜ | 0.00 | — ᶜ | 0.00 | 0.86 (f3) |

### B against N (described, not tested)

| recording · engine | B invented | B D / V | N invented | N D / V |
|---|---|---|---|---|
| air · Gen-4.5 | far end rebuilt as a rounded tub with a tap; second ratchet | 2.33 / 0.93 | recessed panel wall; second, fainter bottle | 0.72 / 1.00 |
| freshwater · Gen-4.5 | bubbles; a grille at the back wall's base | 1.03 / 1.00 | mesh-grating floor; wall streaks | 0.81 / 1.00 |
| basicEnhance · Gen-4.5 | dark room behind a door frame | 1.37 / 1.00 | leaves: rails, ribbed hatch, machine corridor | 4.22 / 1.00 |
| saltwater · Gen-4.5 | built room with a staircase behind the far end | 2.70 / 1.00 | leaves: ribbed turbine-like duct with a light | 3.88 / 1.00 |
| pellets · Gen-4.5 | snow-like pellet layer; tiled wall with a door frame (past the cap) | — ᶜ / 0.00 ᶜ | leaves: pipe, then a gun barrel over a field (past the cap) | — ᶜ / 0.00 ᶜ |
| air · Wan | a walking person (tracked); tank becomes a hallway | 1.23 / 0.98 | dark flash (f72–84), then a military tank | — ˡ / — ˡ |
| freshwater · Wan | a small blob; a trouser leg at the edge at f120 (untracked); slow pull-back | 1.24 / 0.23 | a military tank driving in (tracked) | 2.27 / 0.65 |
| basicEnhance · Wan | nothing | 0.71 / 1.00 | nothing | 0.83 / 1.00 |
| saltwater · Wan | three people (tracked) | 3.89 / 0.54 | leaves: outdoor yard and sky (untracked) and a military tank (tracked) | 3.76 / 0.54 |
| pellets · Wan | a ghostly person (tracked) | 0.88 / 0.92 | nothing | 0.63 / 0.90 |

- **Gen-4.5:** N scores the higher D on the two recordings where N leaves the tank with values (basicEnhance 4.22 against B's 1.37; saltwater 3.88 against 2.70). On air and freshwater, where N only reskins surfaces, N sits below B and under 1 (0.72, 0.81). Every Gen-4.5 B and N with values holds V at 0.93–1.00: the inventions sit on verified pixels. Pellets' pair is past the cap on both.
- **Wan:** what moves V is tracking, not the prompt. Clips with a tracked actor lose V (saltwater B and N both 0.54, freshwater N 0.65); the one big V drop without a track is freshwater B's pull-back (0.23). D runs high where actors fill the frame (saltwater B 3.89, N 3.76) and sits at 0.63–0.88 where nothing was invented.
- **In one line:** on Gen-4.5, N swaps the world and D follows it; on Wan, both prompts add actors, V drops where they're tracked, and D rises where they fill the frame.

### Floors, travel and leaving the tank

**Floors per recording.**

| recording | floor | far end (su) | trusted travel cap (su) | null-dream D median |
|---|---|---|---|---|
| air | 0.208 | 947 | none | 1.33 |
| freshwater | 0.127 | 859 | none | 0.90 |
| basicEnhance | 0.125 | 837 | none | 0.71 |
| saltwater | 0.142 | 814 | none | 0.68 |
| pellets | 0.177 | 706 | 100.0 | 0.68 |

**How far each dream travelled.**

| clip | travel (su) | forward max (su) | first D>3 | wall frame | unverifiable from |
|---|---|---|---|---|---|
| air · Gen-4.5 · B · 5s | 346 | 343 | — | none | — |
| air · Gen-4.5 · D · 5s | 395 | 395 | — | none | — |
| air · Gen-4.5 · N · 5s | 491 | 491 | — | none | — |
| air · Gen-4.5 · D · 10s | 468 | 467 | — | none | — |
| air · Wan · B · 5s | 525 | 523 | — | none | — |
| air · Wan · D · 5s | 120 | 118 | — | none | — |
| air · Wan · N · 5s | 1 | 0 | — | none | f74 (path lost) |
| freshwater · Gen-4.5 · B · 5s | 446 | 444 | — | none | — |
| freshwater · Gen-4.5 · D · 5s | 420 | 419 | — | none | — |
| freshwater · Gen-4.5 · N · 5s | 260 | 259 | — | none | — |
| freshwater · Gen-4.5 · D · 10s | 198 | 198 | — | none | — |
| freshwater · Wan · B · 5s | 232 | 0 | — | none | — |
| freshwater · Wan · D · 5s | 5 | 2 | — | none | — |
| freshwater · Wan · N · 5s | 24 | 0 | — | none | — |
| basicEnhance · Gen-4.5 · B · 5s | 530 | 529 | — | none | — |
| basicEnhance · Gen-4.5 · D · 5s | 267 | 266 | — | none | — |
| basicEnhance · Gen-4.5 · N · 5s | 773 | 773 | f88 | none | — |
| basicEnhance · Gen-4.5 · D · 10s | 427 | 426 | — | none | — |
| basicEnhance · Wan · B · 5s | 64 | 63 | — | none | — |
| basicEnhance · Wan · D · 5s | 235 | 235 | — | none | — |
| basicEnhance · Wan · N · 5s | 47 | 47 | — | none | — |
| saltwater · Gen-4.5 · B · 5s | 495 | 490 | — | none | — |
| saltwater · Gen-4.5 · D · 5s | 357 | 357 | — | none | — |
| saltwater · Gen-4.5 · N · 5s | 706 | 703 | — | none | — |
| saltwater · Gen-4.5 · D · 10s | 504 | 501 | — | none | — |
| saltwater · Wan · B · 5s | 207 | 201 | f102 | none | — |
| saltwater · Wan · D · 5s | 10 | 1 | — | none | — |
| saltwater · Wan · N · 5s | 424 | 423 | f97 | none | — |
| pellets · Gen-4.5 · B · 5s | 99 (held path 462) | 98 (held path 447) | — | none | f30 (travel cap) |
| pellets · Gen-4.5 · D · 5s | 100 (held path 358) | 99 (held path 353) | — | none | f41 (travel cap) |
| pellets · Gen-4.5 · N · 5s | 95 (held path 555) | 94 (held path 550) | — | none | f20 (travel cap) |
| pellets · Gen-4.5 · D · 10s | 100 (held path 408) | 100 (held path 405) | — | none | f62 (travel cap) |
| pellets · Wan · B · 5s | 2 | 2 | — | none | — |
| pellets · Wan · D · 5s | 121 | 0 | — | none | — |
| pellets · Wan · N · 5s | 13 | 0 | — | none | — |

"Held path" is the full path in `runs/clips.json`; the assets keep only the trusted part (pellets' cap). Travel is the straight-line distance to the last held frame; a camera that backs away (freshwater Wan B, pellets Wan D) shows travel with a forward max of 0.

- **Left the tank (by eye, round 2):** basicEnhance Gen-4.5 N (machine corridor), saltwater Gen-4.5 N (duct), pellets Gen-4.5 N (gun barrel, outdoors), air Wan B (hallway), saltwater Wan N (outdoor yard). Saltwater and basicEnhance Gen-4.5 B open the far end into a room but keep the tank's walls.
- **No clip has a wall frame.** As the 3.3 review states, that is the frozen test working as designed: the tracks path lifts its features with the tank map's own depth, so once a dream goes through the far end the recovered camera is pinned in front of the tank's surfaces and can't cross it (basicEnhance Gen-4.5 N stops at 773 su against an 837 su far end, though by eye it is past the back wall by about f72–84). D carries the departure instead: first sustained D>3 at f88 there and f97 on saltwater Wan N. Saltwater Gen-4.5 N crosses 3 at f116, too late for a 12-frame run; air Wan B never holds above 3; pellets N is past its cap. How to state this on the page is **call 77, open for Aaron**.
- **Beyond the validated range:** 19 of 20 Gen-4.5 paths pass the self-test's 200 su; the three saltwater clips past about 430 su (Gen-4.5 B, N and D 10 s) rest on the dream's own texture there (3.3's limit). Path disagreement and its scale are **call 78**; air Wan N's mask from f70 is **call 79**. Both open for Aaron.

### Each clip's map

Flares are read against the clip's own frame 0. Every heat starts with a pale far-end rectangle, which is the noise floor itself (the floor previews put DA3's error there), not an invention.

| clip | what was invented, where it flared, where verification ran out |
|---|---|
| air · Gen-4.5 · B | The far end becomes a tub with a tap from f60; it stays pale tan and the top edge turns to hatch from f96 as the camera rises past the reconstruction. D climbs from 1.08 at 2.5 s to 2.33 at f120. |
| air · Gen-4.5 · D | The second ratchet (f60) lightens the left wall's blue a little; the bottle and floor stay dark. D falls to 0.60 as the bottle fills the frame. Nothing unverified. |
| air · Gen-4.5 · N | The recessed panel wall shows as a pale patch on the left wall at f72; the second bottle doesn't register. D 0.72. |
| air · Gen-4.5 · D · 10 s | A pale tan band spreads across the top third from f168 as the colour turns teal and the second clamp passes; D peaks at 2.46 at f196, then fades to 1.16. |
| air · Wan · B | The person (f36 on) is drawn pale tan inside an outline; the left wall flares pale blue at f36–48 as the tank turns hallway (D 3.14 at f40, the only spike). The hallway then reads dark again (D 1.23). |
| air · Wan · D | No change from frame 0's pattern. D 0.85. |
| air · Wan · N | Holds until the flash; at f72 a pale-blue wash under an outline on the dark mass, then hatch from f74 (path lost). The military tank (f96 on) is never measured. |
| basicEnhance · Gen-4.5 · B | The dark room behind the door frame turns the far end from tan to pale blue by f96–120: it reads deeper than the real back wall. D 1.37; all verified. |
| basicEnhance · Gen-4.5 · D | The striped bars don't register; the far end darkens as the camera closes. D 0.62. |
| basicEnhance · Gen-4.5 · N | The recess and rails at f60, then the ribbed hatch and corridor from f72, flare pale blue across the centre on verified pixels, with a pale tan slab where the hatch frame stands nearer than the tank (f72). D 3.12 at f72, 5.37 at f105, 4.22 at f120. |
| basicEnhance · Gen-4.5 · D · 10 s | The rippling water surface (f96–192) reads almost flat: the top band stays dark. D stays at or under 1.15. |
| basicEnhance · Wan · B / D / N | Frame 0's pattern throughout; D's far end darkens as Wan pushes in 235 su. D 0.71 / 0.72 / 0.83, V 1.00. |
| freshwater · Gen-4.5 · B | Neither the bubbles nor the grille shows; the frame darkens to an even dark blue by f120. D 1.03. |
| freshwater · Gen-4.5 · D | The back wall goes dark blue by f96 and the whole frame follows. D 1.33 at f120, on the lowest-but-one floor (0.127), so small residuals score. |
| freshwater · Gen-4.5 · N | The mesh floor (f84 on) shifts the lower frame from blue to dark tan, faintly. D 0.81. |
| freshwater · Gen-4.5 · D · 10 s | The caustics don't register; the heat is steady. D 0.92–1.29 throughout. |
| freshwater · Wan · B | No invention to speak of; hatch closes in from all four edges from f24 as the camera backs out. V 0.23 at f120, the fastest fall without a track. |
| freshwater · Wan · D | Still; a thin hatch strip late. D 0.87, V 0.92. |
| freshwater · Wan · N | The tank is drawn pale tan inside an outline, growing from f24; the background behind it lightens and hatch appears at the edges from f96. D 2.27, V 0.65. |
| pellets · Gen-4.5 · B / D / N / D · 10 s | Hatch from f30 / f41 / f20 / f62. Before the cap, only frame 0's ragged pale far end (pellets' floor 0.177). Every invention (the snow layer and tiled wall, the pipe and gun barrel, the orange bed) falls after the cap. |
| pellets · Wan · B | The ghostly person (f84 on) is outlined; the far-end tan shrinks. D 0.88, V 0.92. |
| pellets · Wan · D | Pull-back: hatch frames the picture from f48; the far end stays pale tan under the green tint. D 1.16, V 0.41. |
| pellets · Wan · N | Frame 0's pattern; a hatch sliver at the edges late. D 0.63, V 0.90. |
| saltwater · Gen-4.5 · B | The staircase room behind the far end flips the far end from tan to pale blue from f72 and fills the centre by f120. D 2.70; all verified. |
| saltwater · Gen-4.5 · D | The haze clears and the whole tank goes dark blue by f96. D 0.76. |
| saltwater · Gen-4.5 · D · 10 s | The rebuilt doorway (f192 on) and the deep-blue shift turn the frame pale blue by f216–240. D 1.78. |
| saltwater · Gen-4.5 · N | The duct flares pale blue in the centre from f72 and covers the frame by f120. D crosses 3 at f116; 3.88 at f120; V 1.00. |
| saltwater · Wan · B | The people are outlined; the held tank behind them turns steadily paler blue from f24 to f120, not just near the people. D 3.89 (sustained from f102), V 0.54. |
| saltwater · Wan · D | Still. D 0.88, V 0.93. |
| saltwater · Wan · N | The military tank is outlined; the yard walls and sky, which are not tracked, flare pale blue from f24, the sky palest by f96–120. D 3.76 (sustained from f97), V 0.54. |

### Gate H's question: does a final's invention sit on verified pixels?

**Yes.** Several finals put a static invention on verified pixels, and the heat flares on it:

- **basicEnhance Gen-4.5 N, f60–f120:** the ribbed hatch and corridor, not in the start frame and on screen for about 49 frames (well past the 12-frame definition), sit on pixels a real camera saw (V 1.00 throughout, no hatch, no outline). D 3.12 at f72, sustained above 3 from f88, 5.37 at f105.
- **saltwater Gen-4.5 N, f72–f120** (the duct; D 3.88 at f120, V 1.00) and **saltwater Gen-4.5 B, f72–f120** (the staircase room; D 2.70, V 1.00).
- **saltwater Wan N, f24–f120:** the outdoor yard and sky, untracked, so measured (D 3.76); the tank inside the outline isn't counted.

Only pellets' inventions sit wholly in hatch. Two limits go with the answer. First, on the clips that leave the tank, the path is pinned to the tank (call 77), so the residual compares the dream with the tank's back wall seen from near it: still a measured lie, but its distance in su is no path claim. Second, mono depth sets its scale per frame, so a large invention moves the residual off its own pixels too (saltwater Wan B's held tank flares while tracked people fill the frame). By call 73's rule the hunt isn't needed; whether to skip it is Aaron's call at Gate H.

### The film's recording and clip (PROVISIONAL, pending Gate H)

- **Pick: basicEnhance · Gen-4.5 · N · 5 s.** The clearest verifiable lie among the finals: the tank opens into a hatch and corridor on seen pixels, D goes from 1.01 at f0 to 5.37 at f105 with V at 1.00, and the onset (f60–f72) happens at 574–638 su, inside the range where renders of this tank hold the path (to about 670 su at 80 % of the far end).
- **Runner-up: saltwater · Gen-4.5 · N · 5 s.** The same kind of lie (the duct, D 3.88, V 1.00), but its flare starts at about 496 su, past saltwater's roughly 430 su limit, so the path there rests on the dream's own texture. If the film wants Wan beside Gen-4.5, saltwater Wan N (yard and sky measured, the tank outlined) is the candidate.
- The fallback rule (where V falls fastest) isn't needed; for the record that's pellets Gen-4.5 N (cap at f20), and without a cap or track, freshwater Wan B (V under 0.5 from f53).

### Hunt

Round 2b has not run (call 73); its table follows Gate H.

## Verify (task 4.6, 4 Nov)

Sonnet 5.5 · high, on Aaron's standing go (hub call 88). Playwright at 1440 and 390, light and dark, against the real `runs/assets`; no spend, nothing pushed or deployed. The method and every decision are in `docs/DESIGN.md` ("Verify pass"); this is the record.

**Counts.** tsc clean. Vitest **295** passed (282 before; new: `worst.test.tsx` 7, the D track 4, the crumb 1, the plan cursor 1). Playwright **168 passed, 12 skipped** (94 and 2 before; the new files are `verify.spec.ts` and `worst.spec.ts`; the 12 skips are the viewport-specific checks that run on one size only), two full runs in a row green, no retry anywhere. Inspector **0 FAIL**.

**Throttled sync** (390 px, CPU 4x): eight scrubs, all three panes on the chosen frame every time (0 apart). Play, Heat view: 63 to 72 paired screens, never more than 1 frame apart (hist 0: 57-64, 1: 6-8), 119 to 120 of 121 frames presented on each video. Play, Bare view: 53 to 57 paired screens, max 1 (0: 47-52, 1: 5-6), 121 of 121. Measured with `requestVideoFrameCallback` (callbacks of two videos in one animation frame share a timestamp, so they saw the same screen) and `seeked`, never `currentTime`. An earlier way of pairing (nearest earlier callback) read 2 and 3 frames apart; that was the pairing, not the page (callbacks coalesce under load), and the shared-timestamp pairing is the one in the test.

**Axe** 4.14.0, all rules: 0 violations of any impact on the default state, with plain words on, and past a cap, at both sizes and both themes. One moderate was found and fixed first (`landmark-unique`: the three plain-words maps shared one name).

**What `break-ui` found** (all fixed, each with a test): a 60-character recording name pushed the page 199 px sideways at 390 (the title's crumbs were nowrap); a path unverifiable from frame 0 drew NaN in the plan view (`cursorAt` read `path.x[-1]`); from frame 0 the real pane gave no reason for being flat; a missing relief atlas left a note describing a still that was not there; a wrapped title could start a line with a separator; an engine name broke after its hyphen in the 768 table. What held: a D of 40 (clamped to the track edge, said as 40.00 in four places), a missing floor preview (its own message, the key stays), no `0.00` for a D or a V anywhere in a dead clip (only times read 0.00 s), the 10 s dive at f240.

**The 4.6 items:** the picker is top-aligned so it holds still when the finding wraps (the title block still grows; reserving two lines would push the first visit's evidence headers below the fold, so not done); the evidence row is two plus one from 761 to 1023; the phone table's crumb no longer starts a line with a separator and keeps its units whole; the picker stays first in Tab order and the scrubber has a second skip link; one key line relates the heat's scale to D; the Prompt legend names B, D and N with a tooltip for each; the D curve's 1-to-3 band is 22 px of 48 (was 15) at the cost of gold excursions drawn about a quarter shorter. **`THREE.Clock` kept** (allow-list entry, now with its reason): r3f 10.0.0-alpha.6 silences it and relief draws, but needs the `/legacy` import and is a pre-release major.

**Held, unchanged:** every figure the facts test traces still traces (the key line's two new figures, the floor and three times it, were added to its set); gold still appears nowhere but where D is above 3 (the source test and the pixel count pass).

## Clearance (task 6.1, 4 Nov)

Opus 5.5 · high, on Aaron's standing go (hub call 88), with the `publish-clearance` skill. Scope: the page (`web/src`, and `web/dist` built with `VITE_MEDIA_BASE=https://example.invalid/divetwin/v1/`), the media in `runs/assets/`, and `THESIS.md`. The repo is not made public tonight; what would block a later flip is listed at the end. No spend, nothing pushed or deployed.

| # | Check | Result |
|---|---|---|
| 1 | `tools/scan-identifiers.sh` (the hub's) on `web/src`, `web/dist`, `THESIS.md`, `runs/assets/clips.json`, `media_manifest.json`, the five `plan.json` and the 35 `path.json`; then every tracked file; then the whole git history (`git log -p --all`) against `clearance-terms.txt` | **Pass.** Clean everywhere, history included |
| 2 | Unpublished research: its method terms ("contour", "refract", "n_eff", "MAE", "under review"), any venue name (not repeated here), "mm" as a unit, "millimetre", ranging-error figures | **Pass after one fix.** `web/src` and the page: "millimetres" only in the statement's "never millimetres"; "mm" only in two unit-rejection tests (not shipped). `web/dist`: every hit is a library (three.js's refraction shader chunks, React's `useInsertionEffect` for "neff", minified names for "mm"). The thesis said "not millimetres, because the tank's flat window scales raw stereo depth and that factor is neither estimated nor used here", which points at a correction factor: rewritten to the statement's own words (fix 2). Tracked repo: nothing further; `baseline_mm` is the dataset's published calibration |
| 2b | The asset JSONs and files: paths, hosts, usernames, IDs | **Pass.** `clips.json`, `plan.json`, `path.json`: relative asset paths, the dataset's own recording names, seeds, sha256s, published intrinsics; no absolute path, host, username, Modal or Runway id. `media_manifest.json` names only the public host. JPEGs carry JFIF only, PNGs no text chunks, the mp4s only an encoder tag. The Runway `gen.mp4`s carry C2PA content credentials (signer "Runway AI, Inc." via Trufo, a timestamp, random instance UUIDs and a thumbnail of the start frame, which is public anyway; no account data): kept, as `assets.py` intends. All 306 manifest files match their sha256 |
| 3 | The dataset citation, from Zenodo itself | **Pass after one fix.** `zenodo.org/api/records/16753748`: version DOI 10.5281/zenodo.16753748, concept DOI 10.5281/zenodo.16753747 (the concept id answers 410 "deleted" as a record because it is not one; one version exists; both DOIs resolve to record 16753748). Zenodo's own APA export cites the version DOI, so 16753748 is right for the page and the thesis; P37's 16753747 also resolves (to the latest version) and is not wrong. Licence cc-by-4.0, creators Smiles, Farkhatdinov, Oh. The page named the dataset only as "the underwater tank stereo dataset": it now carries Zenodo's APA citation verbatim, and so does the thesis (fixes 1, 2). Camera: ZED Mini on the page, in the thesis and in the README |
| 4a | Dataset CC BY 4.0 | **Pass after one fix:** credited; the licence is now linked to its text (CC 4.0 §3(a)(1)(C) asks for the URI), as are CC BY-NC-SA 4.0 and CC BY-NC 4.0 |
| 4b | Derived disparity visuals CC BY-NC-SA 4.0, Stereo Anywhere and Depth Anything V2 credited (call 16, MODELS.md §2) | **Pass** (already held by a test) |
| 4c | Model licences on the credits list against MODELS.md | **Pass.** DA3 Mono-Large Apache-2.0, Stereo Anywhere CC BY-NC-SA 4.0, DAv2 Large CC BY-NC 4.0, SAM 2.1 Apache-2.0, Wan 2.2 Apache-2.0, Runway "via its API"; Open3D correctly absent (call 24) |
| 4d | Runway Terms of Use §5 | **Pass after one fix.** runway.com/terms-of-use, "Last updated October 23, 2026" (the version F5 and P02 read). §5's only clause on Outputs is (viii): not to use the Services or Outputs "to create, train, develop, or improve similar or competitive products or services", nor permit a third party to. §4: Runway claims no ownership of Outputs and "does not restrict your commercial use of your Outputs". No attribution, AI-label or C2PA-keeping duty; "Powered by Runway" applies only to applications built on the API, which this page is not (it plays finished files). Showing Gen-4.5 clips publicly is clearly fine. The one exposure: the page licensed "the heat" CC BY-NC-SA, and the heat is drawn over the generated frame, so an open licence reached Runway output (the StillDrawn §5(viii) question). Fixed by wording: the generated clips and frames are now said to be the engines' output and not under the CC licences (P02's rule: never put an open licence on Runway stills or clips) (fix 1) |
| 4e | Wan 2.2 output terms | **Pass.** Model card re-read 4 Nov: Apache-2.0; "We claim no rights over the your generated contents"; the user is accountable not to share unlawful, harmful or misleading content. The generated people in the Wan clips are invented, not anyone's likeness |
| 5 | Fiction guardrails; company IP | **Pass.** No banned or uncleared fiction name, nothing of the cosmology, no company name, on any public surface or in the history. The five start frames show the tank only, no person |
| 6 | The thesis | **Pass after fix 2.** Every figure re-derived from `runs/assets/clips.json` by `pipeline/tests/test_thesis_facts.py`: 35 clips, 3 prompts, 5 recordings; 3 departures, 2 spikes, 25 under 3, 5 run out (1 path lost, 4 pellets past the 100 su cap); basicEnhance Gen-4.5 N at f88 (3.7 s), 711 su, peak 5.37 at f105, V 1.00; salt-water Wan at f97 and f102; null-dream D medians 0.68 to 1.33. Two were wrong: "V at 0.93 to 1.00" for the clips that go through the far wall (0.93 is air Gen-4.5 B, which does not leave; the two Gen-4.5 clips that do, basicEnhance N and saltwater N, hold V at 1.00 from first frame to last), and "D still climbs to 3.89" behind the tracked people (3.89 is the 5 s reading; the clip's peak is 4.36 at f103). Honest limits present (a reconstruction, uncorrected units, the path pinned to the tank, one take per cell, the floor's spread) |
| 7 | The page's live words, every clip | **Pass.** New `e2e/clearance.spec.ts`: all 35 clips, plain words on and off, body text plus every alt, aria-label and title, against the paper terms; "millimetres" exactly once (the statement); ZED Mini and the DOI present |
| 8 | The name "Dive Twin" / `divetwin` | **Pass.** Recorded: swept 1 Nov (plan §3 defaults: one unrelated GitHub repo), re-swept 3 Nov at task 0.2 (STATUS line 2: an unrelated dive planner and an App Store app use the name; kept by Aaron as a project codename), chosen by Aaron 3 Nov (hub call 5) |

**Fixes.**
1. `65fca9c` web: the credits carry Zenodo's APA citation verbatim with the DOI URL as the link; "Licence texts:" links CC BY 4.0, CC BY-NC-SA 4.0 and CC BY-NC 4.0; a new line keeps the generated clips (Runway Gen-4.5 and Wan 2.2), including the frames under the heat, out of the CC licences. Tests first (`Below.test.tsx`, three new), plus `e2e/clearance.spec.ts`.
2. `36b9fcc` THESIS.md: the two figures above corrected, the units sentence in the statement's words ("never millimetres: the stereo depth is not corrected for the tank's flat window"), the dataset cited from Zenodo, and the generated clips kept out of the licences. Held by `pipeline/tests/test_thesis_facts.py` (written first: 4 failed, then 8 passed).

**Suites after the fixes.** tsc clean; Vitest **298** passed (295 before, plus the three credits tests); pytest **521** passed (8 min 15 s; the eight in `test_thesis_facts.py` new); Playwright **169 passed, 15 skipped** (the new clearance spec runs in desktop-light and skips by design in the other three projects). `web/dist` rebuilt with the placeholder media base and re-scanned: clean.

**Media staging (task 6.2): what to strip.** Nothing inside any file. Upload exactly the 306 keys in `media_manifest.json`; leave out `runs/assets/MEDIA.md` and `runs/assets/media_manifest.json` (the record, not media). Do not re-encode or strip the Runway `gen.mp4`s: their C2PA credentials are the AI disclosure and carry no account data.

**Before the repo goes public (done 4 Nov, see "Going public" below).** `spend.jsonl` held local scratch paths with the macOS username; STATUS named the Modal workspace (gate M); LOG.md line 228 had an absolute local path; the README said "the camera housing's flat port" where the page says "the tank's flat window".

## Publish (task 6.2, 4 Nov)

Sonnet 5.5 · high, on Aaron's standing go (hub call 88), modelled on P37 Feel the Depth. No spend (R2 and Vercel Hobby charged nothing that shows; the media is 279 MB on the existing `stilldrawn-media` bucket under its own prefix). Nothing pushed; the repo stays private.

1. **Media to R2.** `tools/deploy/media.py` (uv script, boto3 pinned): hashes every file against `media_manifest.json` first (306 of 306 match; any mismatch stops the run), then uploads exactly those 306 keys under `divetwin/v1/` with `Cache-Control: public, max-age=31536000, immutable`, the content type and the sha256 as metadata. 306 uploaded in 65 s (279,313,697 bytes); the re-run skipped 306. `verify --r2` (HEAD on the bucket: size, sha256 metadata, cache header, type) and `verify` (HEAD on `https://media.studionephele.com/`) both pass on all 306. `MEDIA.md` and the manifest were not uploaded. The `gen.mp4` files went up byte for byte (C2PA intact). `clips.json` answers 200; a ranged `gen.mp4` answers 206 with `Accept-Ranges: bytes`.
2. **The page.** `tools/deploy/stage.sh` builds with `VITE_MEDIA_BASE=/media/`, stages `deploy/production/` and runs the identifier scan on `web/dist` and `vercel.json` (clean). `tools/deploy/deploy-production.sh` refuses without `GO_LIVE=yes`. Token: new hub file `tools/divetwin.env.op` (a 1Password reference, copied with `cp`); `VERCEL_SCOPE` in this repo's gitignored `.env.local` (copied). Vercel project `divetwin` on the personal team; the live page is `https://divetwin.studionephele.com` (once its DNS record existed; `https://divetwin.vercel.app` stays as a fallback alias).
3. **A defect found and fixed, the one thing that differs from the brief.** The brief's rewrite `/media/:path*` → media host worked for JSON and PNG, but for video it is broken: Vercel's edge caches an external rewrite by URL and ignores `Range`, so the first range it sees is replayed to every later request. `curl -H "Range: bytes=-4096"` on `gen.mp4` returned the whole 1,477,785 bytes with `content-range: bytes 0-1477784/1477785`; `?a=<random>` cache-busters showed the same (MISS, then HIT with the first range's body). In Chromium the Runway `gen.mp4` (moov atom last) failed with `MEDIA_ERR_NETWORK` and the page said "A clip could not be loaded (gen)". It would have passed a 206 header check. Fix: `.mp4` under `/media/` is a 308 redirect to the media host (the `<video>` elements have no `crossOrigin` and nothing draws a video into a canvas or texture, so no CORS is needed); JSON, PNG and JPEG stay a same-origin rewrite. Redeployed; the same suffix and mid-file ranges now return the right bytes (`content-range: bytes 1473689-1477784/1477785`, 4,096 bytes). A fresh Chromium profile plays all three videos with no error. (A browser that loaded the first deploy kept its poisoned immutable responses; only the deploying session had.) The SPA fallback needed `"destination": "/"`, not `/index.html`, with `cleanUrls` on (the first deploy 404ed unknown paths).
4. **Domain.** `vercel domains add divetwin.studionephele.com divetwin` succeeded (run outside the linked folder, where the CLI wants two arguments). Vercel reports it "not configured": the DNS record is missing. **Blocked on Aaron:** the repo's Cloudflare token (`studionephele-cloudflare.env.op`) can read the zone but a read of its DNS records answers 403 "Authentication error", so it cannot create the record; nothing was attempted and no record touched. The record to add in the studionephele.com zone: type CNAME, name `divetwin`, target `cname.vercel-dns.com`, DNS only (grey cloud), as `feelthedepth` has. (Vercel's own check also accepts an A record `76.76.21.21`, DNS only.) Until then the page is live at the clean alias `https://divetwin.vercel.app`.
5. **Live checks, signed out, on `divetwin.vercel.app`.** `/` 200 (and `/?plain=1`); unknown paths 200 (single page); `/media/clips.json` 200 `application/json`, immutable; a ranged `heat.mp4` and `gen.mp4` 308 then 206 with `Accept-Ranges: bytes`; `/assets/index--t0hTpNI.js` 200 immutable. Playwright (fresh profile) at 1440 and 390 px, `?plain=1` too: default clip (freshwater, enhanced, Gen-4.5 N) loads, real, heat and gen videos all `readyState 4` with no error and play to the end on Play, the relief draws (a still plus "Orbit the surfaces" on a phone), no 4xx or 5xx, no console error, no page error; the only notices are three.js's `THREE.Clock` deprecation and Chrome's one-off `GPU stall due to ReadPixels`. No horizontal scroll at 390. Screenshots looked at: fresh-1440.png, fresh-390-plain.png and fresh-390-relief.png (a scratch folder, not kept).
6. **Not done here, by the brief.** No film yet (`web/public/film/` empty; the card's film is another task), no push, repo private. Bandwidth note: the page's JSON and PNG go through Vercel (about 4 MB a clip); the video goes straight from the media host.

## Film (task 5.1, 4 Nov)

Sonnet 5.5 · high, on Aaron's standing go (hub call 88). `film/script.md` is the script (binding words); `tools/film/README.md` has the pipeline. Nothing pushed or deployed; no film section added to the page.

**Narration.** `tools/film/voice.py`, modelled on the StillDrawn explorer's `voice.py` (same studio voice id, acting direction and delivery context, under `op run --env-file=tools/hume.env.op`, key never printed). One batch read of the nine lines: 989 characters, estimated first, free tier, no retake. Reads: 6.8, 7.0, 6.3, 6.2, 7.2, 9.7, 6.5, 6.9 and 2.3 s (58.9 s of speech). The voice only: the gaps are silence, no music.

**The cut.** 69.9 s, not the script's "about 80": the voice sets the pace and read 58.9 s; each line starts 0.8 s after the last one's own trailing silence (1.8 s after line 6), the picture leads each line by 0.4 s, the end card holds 2.6 s. Between 60 and 180 s, as the card requires. 24 fps (the clips' own rate).

**How the picture is made.** Every frame is a still of the built page, captured with the `?clip=<id>&f=<n>` recipe (slider, then wait for `seeked` on all three videos); nothing is a recording of Play. The 5 s clips are stretched to the voice, so the page frames are blended in slow motion (about 0.2x in shots 3 to 6): that is slowed, not the page's own Play. Camera moves are crops of the stills (Lanczos, from the captured pixels). The page is changed only by what a reader can do (Bare, the table's Departure sort, the relief's drag, "Orbit the surfaces" on a phone) and by: the invite put away ("Not now"), the dream pane invisible for the opening beat so it can join, transitions off, and on a phone the sticky bar made static so a tall screenshot does not draw it mid-page. On a phone the Departure sort is pressed through the DOM (the header is visually hidden there).
Shots: 1 real pane alone, push, dream joins (Bare); 2 f0-f60 both panes, heat off; 3 saltwater-pellets Gen-4.5 N (the real pane goes grey at f20 and the page says so); 4 the film's clip, heat on, f40-f72, key strip in view; 5 scrubber close, cursor walks f10 to f92 (D about 1 at f36 to f62, 3.12 at f72, gold from f76); 6 f72-f105, then the camera goes down to the numbers and the plan view; 7 the 35-clip table sorted by Departure (f88, f97, f102 lead), then the relief turning (about -21 to +21 degrees); 8 the whole first screen at f105 (on a phone, the stage); 9 the end card (ink, gold rule, "divetwin.studionephele.com", "Studio Nephele", the disclosure line verbatim). 9:16 is captured at the page's own 390 px phone layout at 2.77x, dark theme; 16:9 at 1920 x 1080, light. Captions are the sentences, timed by the pauses the read itself made; a sentence over 108 characters at 9:16 splits at a comma; none overflows its band (checked in the build).

**Checks.** `ffprobe`: h264 High yuv420p, 24 fps, 1920 x 1080 and 1080 x 1920, 69.875 s; aac LC 48 kHz stereo; moov before mdat (+faststart). EBU R128 on the finished files: -16.1 LUFS, true peak -4.3 dBTP, both cuts. `blackdetect`: none. Console during capture: clean (the known three.js Clock and GL notices are filtered, as in the page's e2e). Contact sheets and posters looked at (both cuts); findings fixed before the final run: the sticky bar drawn across the 9:16 stage, a left-cut legend in shot 5's zoom, a push that clipped the stage's headings, the relief shot's window, "the dream" label cut at the top of a window.

**Things that do not match the script, or that the controller should know.**
1. Length 69.9 s, not about 80 (above).
2. Shot 6's line says the dream "goes through the far wall"; the plan view at f105 shows the camera path (765 su) stopping short of the far wall (837 su), because a tank-anchored path cannot follow a dream out (the page says so under the plan). The picture is the page's own and the line stays the script's.
3. Shot 7's "three leave the tank for good" is read as the three clips with a departure (f88, f97, f102); the table shows them first.
4. The ghosting of the readout digits (two page frames' numerals on top of each other) in slow-motion blends is the blend of two page frames.
5. The 16:9 mp4 is 18.6 MB (CRF 20 at 1080p); P37's was 4.6 MB. If the page serves it from the page host rather than the media host, a higher CRF is a one-line change in `assemble.py`.

**Line 6 retake (4 Nov, on the coordinator's ruling).** Point 2 above was an overclaim: the narration said the dream "goes through the far wall" while the plan view's path stops at 765 su of 837. Line 6 is now "Here, just under four seconds in, the far wall opens into a corridor that isn't there." (`film/script.md`, `tools/film/film.json`); only that line was read again (148 characters, one retake, free tier; `voice.py` replaced its entry in `film/vo/lines.json`). Both aspects recut: 69.4 s, -16.1 LUFS integrated, true peak -4.3 dBTP, no black frames; contact sheets and the shot-6 frames looked at; the 16:9 mp4 and poster are recopied into `web/public/film/`. The plain-words layer's chapter 2 now ends "The back wall opens into a corridor that isn't there." (`web/src/plainwords/words.ts`); tsc clean, Vitest 298 passed. Point 2 of the list above is resolved; the film still shows the plan path short of the wall, which now agrees with the words.

## Going public (4 Nov 2026, hub call 91)

Clearance's pre-flip list was done on the current tree (local paths made relative in `spend.jsonl` and LOG, the Modal account name removed, the README's "flat port" aligned to the page's "flat window", the live page named as `divetwin.studionephele.com` with the Vercel alias as a fallback only, the clearance notes and tests no longer naming a venue, STATUS marked DONE). The identifier scan on the tracked tree is clean.

The full development history was scanned and is **not** published: it carries absolute local paths with the macOS username, the venue names the clearance notes once listed, and a clearance line that spelled out names the scan forbids. Rather than rewrite it, the public repo `aaronlsmiles/divetwin` has one commit, "Dive Twin, as shipped 4 Nov 2026", built from this tree on an orphan branch `public`; the 100-plus commits of working history stay in the private local clone.

Licences: code MIT (`LICENSE`); the dataset CC BY 4.0, the derived depth pictures CC BY-NC-SA 4.0, the generated clips and the film outside any CC licence (`DATA-LICENSE.md`).
