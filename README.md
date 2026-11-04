# Dive Twin

*Follow a generated dive down a real tank, and see how much of the dream can be checked.*

Live: https://divetwin.studionephele.com · Film: [`web/public/film/divetwin-16x9.mp4`](web/public/film/divetwin-16x9.mp4) (also on the page) · Essay: [`THESIS.md`](THESIS.md)

## What it is

A video model is given one real photograph of an empty underwater tank and asked to glide down it. The tank was measured with stereo, so the dream can be checked against the real tank frame by frame. The reference is the real tank, re-seen from wherever the dream took the camera. Where the dream and the measurement both have a surface, a heat map shows how far apart they are. Where no real camera ever looked, the frame is grey and is counted as unverifiable. A plan view shows the path the dream took against the tank's measured walls.

- **The real side:** five recordings from the published UW-TransStereo dataset, one for each water condition (Air, Freshwater, Freshwater-basicEnhance, Saltwater, Saltwater-pellets). The camera is a ZED Mini, fixed at one end of the tank. The tank's depth comes from an off-the-shelf stereo matcher run on the published pairs. That stereo depth is not corrected for the tank's flat window, so every distance here is in uncorrected stereo units.
- **The generated side:** continuations of a real empty-tank frame from Gen-4.5 (Runway) and Wan 2.2 TI2V-5B (open weights). Depth for every generated frame comes from a monocular depth model.
- **Alignment:** one scale and one shift per clip, fitted on the first frame, where the camera is known, and then frozen for the whole clip. After that, the camera path for each frame is recovered by registering its depth to the reconstructed tank.

## What it explores

A video model continues a frame from the published underwater stereo dataset, and the dream is checked against the real recordings, frame by frame, as far as they reach.

## Why it matters

A simulated world is only useful where you can tell it is right. Few scenes a video model can dream come with real stereo recordings to check them against, and this published dataset is one.

## What it suggests

Simulators will ship with measured anchors, and will show where checking runs out.

## How to run

### `pipeline/` (offline, Python)

To be written. The pipeline is a Python 3.12 project managed with uv. It reads the dataset from a local copy (never copied into this repo) and runs its GPU steps on Modal. Download the dataset from Zenodo, then link its `data/` folder at the repo root (`ln -s <dataset>/data data`; the link is gitignored) or set `DIVETWIN_DATA` to its `data/export` folder. Without it, the data tests skip.

### `web/` (the page)

To be written. A Vite, React and TypeScript page that reads `clips.json` and static media; it calls no API.

## Data, models and licences

- **Data:** the UW-TransStereo dataset, CC BY 4.0. This citation is copied from the Zenodo record:

  > Smiles, A., Farkhatdinov, I., & Oh, C. (2025). UW-TransStereo: Underwater Stereo Vision Dataset for Transparent Object Detection & Ranging [Dataset]. Zenodo. RiTA 2025, King's College London. https://doi.org/10.5281/zenodo.16753748

  Concept DOI (all versions): [10.5281/zenodo.16753747](https://doi.org/10.5281/zenodo.16753747).
- **Camera:** ZED Mini (stereo), fixed.
- **Models:** names, pinned revisions and licences are in [`pipeline/MODELS.md`](pipeline/MODELS.md).
- **Real-side depth** comes from Stereo Anywhere (University of Bologna, CVPR 2025; [bartn8/stereoanywhere](https://github.com/bartn8/stereoanywhere)), licensed CC BY-NC-SA 4.0, with its Depth Anything V2 Large prior ([DepthAnything/Depth-Anything-V2](https://github.com/DepthAnything/Depth-Anything-V2)), whose weights are licensed CC BY-NC 4.0. Both are fetched at run time and never vendored into this repo. The disparity visuals this project publishes are licensed CC BY-NC-SA 4.0. This project is non-commercial.

  The authors' citations, copied from the official repositories:

  ```bibtex
  @InProceedings{Bartolomei_2025_CVPR,
      author    = {Bartolomei, Luca and Tosi, Fabio and Poggi, Matteo and Mattoccia, Stefano},
      title     = {Stereo Anywhere: Robust Zero-Shot Deep Stereo Matching Even Where Either Stereo or Mono Fail},
      booktitle = {Proceedings of the Computer Vision and Pattern Recognition Conference (CVPR)},
      month     = {June},
      year      = {2025},
      pages     = {1013-1027}
  }

  @article{depth_anything_v2,
    title={Depth Anything V2},
    author={Yang, Lihe and Kang, Bingyi and Huang, Zilong and Zhao, Zhen and Xu, Xiaogang and Feng, Jiashi and Zhao, Hengshuang},
    journal={arXiv:2406.09414},
    year={2024}
  }
  ```
- **Code:** MIT ([`LICENSE`](LICENSE)). Data, derived pictures, the film and the generated clips have their own terms in [`DATA-LICENSE.md`](DATA-LICENSE.md): the dataset CC BY 4.0, the derived depth pictures CC BY-NC-SA 4.0, the generated clips not under any CC licence.
