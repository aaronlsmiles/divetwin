# MODELS.md: licences and pins (plan task 0.4)

Checked 3 Nov 2026 from primary sources only: the official GitHub repositories (via the GitHub API: LICENSE files, READMEs, commit SHAs), the official Hugging Face model cards and repo API (revision SHAs, licence metadata), and PyPI metadata. Community mirrors were not used as evidence.

Use case: a public, non-commercial portfolio page and a public GitHub repo. Real depth: Stereo Anywhere on the dataset's published rectified pairs.

## Summary

| # | Model | Pin (id @ revision) | Code licence | Weights licence | Allowed on the page? |
|---|---|---|---|---|---|
| 1a | Depth Anything 3 Mono-Large (**primary, generated side**) | `depth-anything/DA3MONO-LARGE` @ `f465978e618db8cc79c83b8bbf24964857db1875`; code `ByteDance-Seed/Depth-Anything-3` @ `3d835ec1a5802d64a8b8b15f817a1ab54809bfe4` | Apache-2.0 | Apache-2.0 | Yes |
| 1b | Depth Anything 3 Metric-Large (secondary, units cross-check) | `depth-anything/DA3METRIC-LARGE` @ `4010e39f3634a45bc60553321fb49fb760bd594e` | Apache-2.0 | Apache-2.0 | Yes |
| 2 | Stereo Anywhere (**real side**) | `bartn8/stereoanywhere` @ `c4aa114b8e4dbba97c41663efb80df95875eeb95`; weights `stereoanywhere_sceneflow.pth` (Google Drive, not revisioned) | CC BY-NC-SA 4.0 | No separate statement; treat as CC BY-NC-SA 4.0 | Yes, conditionally (non-commercial, attribution, share-alike; see section 2) |
| 2b | Depth Anything V2 Large (needed by Stereo Anywhere) | `depth-anything/Depth-Anything-V2-Large` @ `cbbb86a30ce19b5684b7a05155dc7e6cbc7685b9` (`depth_anything_v2_vitl.pth`) | Apache-2.0 (repo) | CC BY-NC 4.0 | Yes, conditionally (non-commercial, attribution) |
| 3 | Wan 2.2 TI2V-5B | `Wan-AI/Wan2.2-TI2V-5B-Diffusers` @ `b8fff7315c768468a5333511427288870b2e9635`; code `Wan-Video/Wan2.2` @ `1ea34ff48f87168174e12956e200b1d908b1c5ff` | Apache-2.0 | Apache-2.0 | Yes (use restrictions apply) |
| 4 | SAM 2.1 | `facebook/sam2.1-hiera-large` @ `665f8e2ad61cf5f53d65644ff27c8ee525124610` (or `sam2.1-hiera-base-plus` @ `b7320756a13354e7530a63935656d35b2f91a290`); code `facebookresearch/sam2` @ `2b90b9f5ceec907a1c18123530e92e794ad901a4` | Apache-2.0 | Apache-2.0 | Yes |
| 5 | Open3D | PyPI `open3d==0.20.0` (cp312 wheels for macOS arm64 and Linux x86_64/aarch64); repo tag `v0.20.0` | MIT | n/a | Yes |
| 6a | Video Depth Anything (fallback) | `depth-anything/Video-Depth-Anything-Small` @ `256875362cff76724b920335dfb4b29dd611f66e` | Apache-2.0 (repo) | Small: Apache-2.0; **Large: CC BY-NC 4.0** | Small yes; Large non-commercial only |
| 6b | Depth Anything V2 Metric (fallback) | `depth-anything/Depth-Anything-V2-Metric-Hypersim-Large` @ `79720800638389a78b2defc92caa885104f69974` | Apache-2.0 | Apache-2.0 (HF card) | Yes |

**Blockers: none outright.** Two things to know before Gate 0 is treated as closed:

1. **Stereo Anywhere is non-commercial and share-alike (CC BY-NC-SA 4.0), and its weights come with no licence of their own.** The runtime also needs the Depth Anything V2 **Large** weights (CC BY-NC 4.0). Both are usable for a public non-commercial portfolio page. They are the only non-Apache items in the pipeline, so the page and repo must carry the attribution and the non-commercial statement, and the repo must not redistribute either weights file. OpenCV SGBM stays the fallback if Aaron reads "portfolio used to apply for jobs" as too close to commercial use.
2. **The `depth-anything-3` PyPI package is unreliable as a pin.** Version 0.1.1 exists (uploaded 4 Mar 2026, author field "Your Name", homepage the official repo), but the official repo's `pyproject.toml` says `version = "0.0.0"`. Install from the pinned git commit instead.

## 1. Depth Anything 3 (ByteDance Seed)

- **Code:** `https://github.com/ByteDance-Seed/Depth-Anything-3`, commit `3d835ec1a5802d64a8b8b15f817a1ab54809bfe4` (main, last push 27 Jul 2026). LICENSE is Apache-2.0 (full text); `pyproject.toml` declares `name = "depth-anything-3"`, `version = "0.0.0"`, `license = Apache-2.0`, `requires-python = ">=3.9, <=3.13"`.
- **Package:** `pip install "git+https://github.com/ByteDance-Seed/Depth-Anything-3@3d835ec1a5802d64a8b8b15f817a1ab54809bfe4"` (import name `depth_anything_3`; the README uses `DepthAnything3.from_pretrained(...)`). PyPI has `depth-anything-3` 0.1.0 and 0.1.1 (Apache-2.0 metadata) but the unversioned repo pyproject makes the git commit the safer pin. The Gaussian-splat head needs `gsplat`, which we do not need; install the basic extra only.
- **Licence table** (README "Model Zoo", read at the commit above; cross-checked against each model card's `license:` field):
  - Apache-2.0: `DA3METRIC-LARGE`, `DA3MONO-LARGE`, `DA3-BASE`, `DA3-SMALL`.
  - CC BY-NC 4.0: `DA3-LARGE`, `DA3-LARGE-1.1`, `DA3-GIANT`, `DA3-GIANT-1.1`, `DA3NESTED-GIANT-LARGE`, `DA3NESTED-GIANT-LARGE-1.1`.
  - So the plan's belief is right for Mono and Metric Large, with one correction: the any-view **Large** is CC BY-NC (as is Giant), and only the any-view Base and Small are Apache-2.0.
- **Checkpoint to pin (generated side): `depth-anything/DA3MONO-LARGE`**, revision `f465978e618db8cc79c83b8bbf24964857db1875` (0.35 B parameters, files `config.json`, `model.safetensors`; card says `license: apache-2.0`). Reason: the plan fits one scale and one shift per clip in inverse-depth space, so relative depth is all it needs, and the Mono series is the dedicated high-quality relative model. Source: `https://huggingface.co/depth-anything/DA3MONO-LARGE`.
- **Secondary: `depth-anything/DA3METRIC-LARGE`**, revision `4010e39f3634a45bc60553321fb49fb760bd594e` (Apache-2.0). Metric depth is `focal_px * net_output / 300` (README), useful as a units cross-check against the stereo baseline. Source: `https://huggingface.co/depth-anything/DA3METRIC-LARGE`.
- **Do not use** any CC BY-NC checkpoint above; even though the page is non-commercial, keeping the generated side Apache-2.0 means it is the one part of the pipeline with no attribution-or-NC conditions.
- **Why allowed:** Apache-2.0 for code and both weights permits public, non-commercial (and commercial) use and redistribution of outputs, with licence and notice retained. Add a NOTICE line crediting ByteDance Seed.

## 2. Stereo Anywhere (CVPR 2025; University of Bologna)

- **Official code:** `https://github.com/bartn8/stereoanywhere`, commit `c4aa114b8e4dbba97c41663efb80df95875eeb95` (main, last push 30 Jun 2026). The repo README is the CVPR 2025 paper's page (title, arXiv 2412.04472, authors' README). GitHub's API reports the licence as NOASSERTION because `LICENCE.md` is a custom-headed file: "Copyright (c) 2024 University of Bologna. All rights reserved." followed by the full text of **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)**. Read at `https://github.com/bartn8/stereoanywhere/blob/main/LICENCE.md`.
- **Official weights:** the README's "Pretrained Models" section links one Google Drive folder, `https://drive.google.com/drive/folders/1uQqNJo2iWoPtXlSsv2koAt2OPYHpuh1x`. Contents (read from the folder page): `stereoanywhere_sceneflow.pth` (43.8 MB, the model to use), `sceneflow.tar`, `raftstereo-realsceneflow.pth`, `boosterft.zip`, plus MonoTrap and mask archives. **No licence text sits in or beside the weights and there is no model card or Hugging Face release.** The only licence statement from the authors is the repo-level CC BY-NC-SA 4.0, so treat the weights as under it. Drive files have no revision: record the SHA-256 of `stereoanywhere_sceneflow.pth` at first download in `runs/` and in this file.
- **Monocular prior it actually needs:** `--monomodel DAv2` with `--loadmonomodel weights/depth_anything_v2_vitl.pth` and `--vit_encoder vitl` (default). The README's eval and demo commands use "DAv2-Large", and the training preprocessing was done with it. The repo vendors the Depth Anything V2 model code under `models/depth_anything_v2/` (code is Apache-2.0 upstream) but **not** the weights.
  - **Weights to fetch:** `depth-anything/Depth-Anything-V2-Large`, revision `cbbb86a30ce19b5684b7a05155dc7e6cbc7685b9`, file `depth_anything_v2_vitl.pth`. Model card and Depth-Anything-V2 README: **CC BY-NC 4.0** (Small is Apache-2.0, Base/Large/Giant are CC BY-NC 4.0). Sources: `https://huggingface.co/depth-anything/Depth-Anything-V2-Large`, `https://github.com/DepthAnything/Depth-Anything-V2`.
  - Swapping to the Apache-licensed Small (`--vit_encoder vits`) is supported by the flags but the stereo checkpoint was trained against the Large prior; a mismatched prior is untested and would need a quality check. Not recommended unless Large is ruled out.
- **Other dependencies** (`requirements.txt`): `torch==2.4.0+cu121`, `torchvision==0.19.0+cu121`, `xformers==0.0.27.post2`, `timm==1.0.15`, plus albumentations, cmapy, kornia, matplotlib, numba, numpy, opencv_contrib_python, opencv_python, opt_einsum, Pillow, scikit_learn, tqdm. Pin the Modal image to these CUDA 12.1 wheels. Training data for the stereo weights is Sceneflow only (synthetic).
- **May the weights be used for a public non-commercial page?** Yes. CC BY-NC-SA 4.0 permits use, reproduction and sharing for non-commercial purposes with attribution. A free, non-monetised portfolio page and public repo is non-commercial in the ordinary sense.
- **May the derived disparity maps be published?** The licence does not mention model outputs. Outputs of a model are not obviously "Adapted Material" of the code or weights, so the NC and SA conditions are most plausibly not triggered by the maps themselves. Safest course, and what to do: publish disparity visuals with attribution ("Stereo Anywhere, Bologna, CVPR 2025, CC BY-NC-SA 4.0; Depth Anything V2, CC BY-NC 4.0") and a non-commercial statement, and license the page's derived disparity images CC BY-NC-SA 4.0 so that either reading is satisfied. Keep raw `.npz` disparity under `runs/disp/` (gitignored) and out of the public repo.
- **What the public repo must not do:** copy Stereo Anywhere code, vendored DAv2 code or either weights file into the repo (share-alike would then govern that code, and the weights' redistribution terms are unstated). Fetch them at run time on Modal from the sources above; the repo holds only our own `modal_stereo.py` that calls them.
- **Judgement call for Aaron (not a blocker):** NC terms are defined by "primarily intended for or directed toward commercial advantage or monetary compensation". A portfolio page that supports a job application is not itself sold or monetised, and this is the standard reading for academic/portfolio use, but it is a reading, not a ruling. If he wants zero ambiguity, either email the authors (Bologna CVLab) for a one-line confirmation or take the SGBM fallback.
- **Fallback:** OpenCV SGBM (`cv2.StereoSGBM_create`, Apache-2.0 for OpenCV 4.5+), classical, same calibration and rectified pairs. Holey in milky water but licence-trivial.

## 3. Wan 2.2 TI2V-5B (Wan-AI)

- **Model:** `Wan-AI/Wan2.2-TI2V-5B-Diffusers`, revision `b8fff7315c768468a5333511427288870b2e9635` (last modified 9 Aug 2025). Card front-matter: `license: apache-2.0`. Source: `https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B-Diffusers`.
- **Code:** `https://github.com/Wan-Video/Wan2.2`, commit `1ea34ff48f87168174e12956e200b1d908b1c5ff`, Apache-2.0. Generation runs through diffusers (`WanPipeline`, `AutoencoderKLWan`). The card notes the model needs features in diffusers main at the time of writing: check the diffusers release on the Modal image and pin it, or pin a diffusers git commit if the stable release lacks `WanPipeline` TI2V support.
- **Use restrictions (card "License Agreement" section):** weights are Apache-2.0; Wan claims no rights over generated content; the user is "fully accountable" for use and must not share content that violates applicable laws, causes harm to individuals or groups, disseminates personal information intended for harm, spreads misinformation, or targets vulnerable populations. The full text is in the repo's `LICENSE.txt` (Apache-2.0). None of this affects an underwater tank time-lapse.
- **Why allowed:** Apache-2.0 plus a "your content, your responsibility" clause; a public non-commercial page is plainly within terms. Credit Wan-AI in the page footer.

## 4. SAM 2 / SAM 2.1 (Meta FAIR)

- **Code:** `https://github.com/facebookresearch/sam2`, commit `2b90b9f5ceec907a1c18123530e92e794ad901a4`. LICENSE Apache-2.0. README "License": "The SAM 2 model checkpoints, SAM 2 demo code (front-end and back-end), and SAM 2 training code are licensed under Apache 2.0" (the demo's Inter font and Noto Color Emoji are SIL OFL 1.1, not used by us; `LICENSE_cctorch` is a BSD-3-Clause file for a bundled connected-components snippet).
- **Checkpoint to pin:** the SAM 2.1 video predictor, **`facebook/sam2.1-hiera-large`**, revision `665f8e2ad61cf5f53d65644ff27c8ee525124610` (card `license: apache-2.0`; files include `sam2.1_hiera_large.pt` and `sam2.1_hiera_l.yaml`). Official release URL for the same weights: `https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt`. If memory or speed matters, `facebook/sam2.1-hiera-base-plus` @ `b7320756a13354e7530a63935656d35b2f91a290` is also Apache-2.0. Use the SAM 2.1 (not original SAM 2) checkpoints with the repo commit above.
- **Why allowed:** Apache-2.0 for code and weights.

## 5. Open3D

- **Version:** `open3d==0.20.0` on PyPI (MIT); GitHub release `v0.20.0` published 16 Sep 2026. PyPI lists CPython 3.12 wheels: `open3d-0.20.0-cp312-cp312-macosx_11_0_arm64.whl`, `open3d-0.20.0-cp312-cp312-manylinux_2_35_x86_64.whl` and `..._aarch64.whl` (also win_amd64). Repo `LICENSE` is the MIT licence. Source: `https://github.com/isl-org/Open3D`, `https://pypi.org/project/open3d/0.20.0/`.
- Linux wheels need glibc 2.35 or newer (Ubuntu 22.04+); check the Modal base image.
- **Why allowed:** MIT.

## 6. Fallbacks (kill rule 1)

- **Video Depth Anything** (`https://github.com/DepthAnything/Video-Depth-Anything`, commit `4f5ae23172ba60fd7bc11ef671cca678842c7072`, Apache-2.0 repo). Weights: **Small is Apache-2.0** (`depth-anything/Video-Depth-Anything-Small` @ `256875362cff76724b920335dfb4b29dd611f66e`); **Large is CC BY-NC 4.0** (`depth-anything/Video-Depth-Anything-Large` @ `7aafbcb5c6af0bac741aad2b6471894fb4761afa`), usable on this page only because it is non-commercial. Prefer Small if the fallback fires.
- **Depth Anything V2 Metric** (`https://github.com/DepthAnything/Depth-Anything-V2`, `metric_depth/`, Apache-2.0 repo). Metric checkpoints on Hugging Face carry `license: apache-2.0` in their cards (Hypersim Large @ `79720800638389a78b2defc92caa885104f69974`, Base @ `4ebcd7fd0858cbb953451619ca943ea39ec08e00`, Small @ `3bc65d4e14a6786a61acec16453c50e12bf5f338`). Caveat: the upstream README's relative-depth table lists Base/Large as CC BY-NC while the metric cards say Apache-2.0; the metric README does not state a licence either way. The metric fine-tunes sit on the CC BY-NC relative encoders, so if this fallback is used, treat it as non-commercial-only in the attribution line.

## Attribution block for the page and repo NOTICE

Depth Anything 3 (ByteDance Seed, Apache-2.0); Stereo Anywhere (University of Bologna, CVPR 2025, CC BY-NC-SA 4.0); Depth Anything V2 (HKU/TikTok, Large weights CC BY-NC 4.0); Wan 2.2 (Wan-AI, Apache-2.0); SAM 2.1 (Meta FAIR, Apache-2.0); Open3D (MIT). This page is non-commercial.

## Modal image pins (provisional until the first build)

Nothing below has been built: the images are only ever resolved on Modal, and no remote call has been made. Each floating package was pinned to the PyPI release nearest the pinned torch (dates from PyPI) and must be confirmed by the first build; if the resolver objects, the likely culprits are the ones marked with an asterisk.

- **Stereo image** (torch 2.4.0, 24 Jul 2024; Python 3.11): `kornia==0.7.3` (28 Jun 2024), `opt_einsum==3.4.0` (26 Sep 2024; 3.3.0 dates from 2020)*, `matplotlib==3.9.1` (4 Jul 2024), `huggingface_hub==0.24.0` (18 Jul 2024)*, `Pillow==10.4.0` (1 Jul 2024); `numpy<2` stays. The authors' requirements (`timm==1.0.15`, `xformers==0.0.27.post2`) were already exact.
- **DA3 image** (torch 2.5.1, 29 Oct 2024): the package itself installs with `--no-deps` at the pinned commit. DA3's `pyproject.toml` at that commit lists 26 dependencies (`pre-commit`, `trimesh`, `open3d`, `fastapi`, `uvicorn`, `e3nn`, `gsplat`, `pycolmap`, `evo`, `moviepy==1.0.3`, ...); `api.py` imports the export and pose modules at module level, so the inference path needs, and the image installs, only: `einops==0.8.0`, `omegaconf==2.3.0`, `addict==2.4.0`, `tqdm==4.66.5`, `safetensors==0.4.5`, `imageio==2.36.0`, `matplotlib==3.9.2`, `moviepy==1.0.3`*, `plyfile==1.1`, `pycolmap==3.10.0`*, `trimesh==4.5.0`, `scipy==1.14.1`, `packaging==24.1`, and `evo==1.30.4` with `--no-deps` (`pose_align` imports only `evo.core.trajectory`, which needs numpy, scipy and packaging). `huggingface_hub==0.26.2` (28 Oct 2024), `Pillow==11.0.0` (15 Oct 2024). Left out on purpose: `open3d`, `fastapi`, `uvicorn`, `typer`, `requests`, `pre-commit`, `e3nn` (guarded import), `gsplat` (guarded, 3DGS only), `pillow_heif`. If DA3 fails to import, read the traceback for the missing module and add it here; `moviepy.editor` (1.0.3 only) is why that old pin stays.
- **SAM 2 image**: `huggingface_hub==0.26.2`, `setuptools==75.1.0` (16 Sep 2024), `wheel==0.44.0` (4 Aug 2024), for the `--no-build-isolation` install.
- **Weights function** (CPU only): `huggingface_hub==0.24.0` and `gdown==5.2.0` (stereo), `huggingface_hub==0.26.2` (depth).
- **Wan image** (`modal_wan.py`, torch 2.5.1 as the DA3 image; Python 3.11): `diffusers==0.35.1` (the line that carries the Wan 2.2 TI2V transformer config; the model's `model_index.json` says 0.35.0.dev0), `transformers==4.55.0` and `huggingface_hub==0.34.4` (the pair diffusers 0.35 requires), `accelerate==1.10.0`, `safetensors==0.4.5`, `sentencepiece==0.2.0` (the UMT5 tokenizer), `ftfy==6.3.1` (diffusers' Wan prompt cleaning imports it), `numpy<2`, `Pillow==11.0.0`, `av==13.1.0` (the mp4 encoder; its wheel bundles FFmpeg). Weights function (CPU only): `huggingface_hub==0.34.4`. Unbuilt: the first build is the smoke run (`2.4-wan-smoke`, cap $0.70); if the resolver or an import objects, read the traceback, fix the pin here, and say so in LOG.md.
- **Wan 2.2 settings** (from the model card's example): `AutoencoderKLWan` in float32, the pipeline in bfloat16, 1280 x 704, 121 frames, 24 fps, 50 steps, guidance 5.0. Image conditioning through `WanImageToVideoPipeline` (the checkpoint's `expand_timesteps` is true); no negative prompt, so the words D, B and N are the only steering on both engines.

## Open items

- Recorded 2026-11-03 by the CPU-only `fetch_weights` (also in `runs/disp/weights.json`): SHA-256 of `stereoanywhere_sceneflow.pth` = `ea5c0352facae2b0fd33d293fbb59f290ec907a04940aaeb626d8d2c7b55acb2`; SHA-256 of `depth_anything_v2_vitl.pth` = `a7ea19fa0ed99244e67b624c72b8580b7e9553043245905be58796a608eb9345`. The DA3 and SAM 2 files are recorded the same way (`depth_weights_sha256.json`).
- Image pins are **provisional until the first build** (see below): the first `modal run` is also the first time the images are resolved.
- Confirm on the Modal image that diffusers has Wan 2.2 TI2V support (pin the version).
- Aaron's call: accept the NC reading for Stereo Anywhere, or ask the authors, or take SGBM.
