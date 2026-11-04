# Data and media licences

The code is MIT ([`LICENSE`](LICENSE)). Everything else in and around this repo is covered here.

## The real recordings and labels: CC BY 4.0

The tank recordings come from the **UW-TransStereo** dataset, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/):

> Smiles, A., Farkhatdinov, I., & Oh, C. (2025). UW-TransStereo: Underwater Stereo Vision Dataset for Transparent Object Detection & Ranging [Dataset]. Zenodo. RiTA 2025, King's College London. https://doi.org/10.5281/zenodo.16753748

The dataset is **not** in this repo; the pipeline reads a local copy. Camera: ZED Mini, fixed.

## Depth pictures and relief made from the recordings: CC BY-NC-SA 4.0

The disparity and depth visuals this project publishes (the tank relief, the plan views, the heat maps and the small fixtures in `web/src/test/fixtures/`) are derived from the dataset by [Stereo Anywhere](https://github.com/bartn8/stereoanywhere) (University of Bologna, CVPR 2025, CC BY-NC-SA 4.0) with its Depth Anything V2 Large prior (weights CC BY-NC 4.0). They are licensed [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), so either reading of those terms is satisfied. Attribution: "Stereo Anywhere, Bologna, CVPR 2025; Depth Anything V2; UW-TransStereo (CC BY 4.0)". This project is non-commercial. Neither model's code nor weights are vendored here; pinned revisions and licences are in [`pipeline/MODELS.md`](pipeline/MODELS.md).

## Generated clips and frames: not under any CC licence

The video clips and frames come from **Runway Gen-4.5** (via its API) and **Wan 2.2 TI2V-5B** (Apache-2.0 weights; Wan claims no rights over its output). They are the engines' output, are **not** covered by the CC licences above, and are shown on the page and in the film as the subject of the study. The 35 clips are not in this repo (`runs/` and `*.mp4` are ignored); the one film that is, below, contains some of them.

## The film (`web/public/film/`)

`divetwin-16x9.mp4` and its poster are screen captures of the page with generated clips inside them, plus a narration read by Hume (Octave text-to-speech, studio voice, free tier). It is not under the CC licences above (the generated-clip notice applies to what is in it); copyright Aaron Smiles for the capture, edit and narration arrangement.

## Fonts

Geist and Geist Mono are licensed under the SIL Open Font License 1.1 (`web/public/fonts/OFL.txt`).
