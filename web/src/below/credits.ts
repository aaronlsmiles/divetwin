// Credits. Static text, so a figure here (licence versions, model versions, the DOI) is a name, not a measurement.
/** `citation` is Zenodo's own APA export of the record (zenodo.org/api/records/16753748, fetched 4 Nov 2026 for clearance 6.1), copied
 *  verbatim: never from a paper's bib (P37's lesson). 16753748 is the version DOI Zenodo cites; 16753747 is the concept DOI (all versions). */
export const DATASET = {
  text: "The underwater tank stereo dataset, recorded with a ZED Mini camera. CC BY 4.0.",
  doi: "10.5281/zenodo.16753748",
  citation: "Smiles, A., Farkhatdinov, I., & Oh, C. (2025). UW-TransStereo: Underwater Stereo Vision Dataset for Transparent Object Detection & Ranging [Dataset]. Zenodo. RiTA 2025, King's College London. https://doi.org/10.5281/zenodo.16753748",
};

/** Each Creative Commons licence the credits name, linked to its text (CC 4.0 section 3(a)(1)(C) asks for the URI). */
export const LICENCES: { name: string; url: string }[] = [
  { name: "CC BY 4.0", url: "https://creativecommons.org/licenses/by/4.0/" },
  { name: "CC BY-NC-SA 4.0", url: "https://creativecommons.org/licenses/by-nc-sa/4.0/" },
  { name: "CC BY-NC 4.0", url: "https://creativecommons.org/licenses/by-nc/4.0/" },
];

/** From pipeline/MODELS.md's attribution block, plus the two generators. */
export const MODELS: { name: string; by: string; licence: string; used: string }[] = [
  { name: "Depth Anything 3 (Mono-Large)", by: "ByteDance Seed", licence: "Apache-2.0", used: "depth of the generated clips" },
  { name: "Stereo Anywhere", by: "University of Bologna, CVPR 2025", licence: "CC BY-NC-SA 4.0", used: "the real tank's depth from the stereo pairs" },
  { name: "Depth Anything V2 (Large weights)", by: "HKU and TikTok", licence: "CC BY-NC 4.0", used: "the prior Stereo Anywhere needs" },
  { name: "SAM 2.1", by: "Meta FAIR", licence: "Apache-2.0", used: "tracking things that move" },
  { name: "Wan 2.2 (TI2V-5B)", by: "Wan-AI", licence: "Apache-2.0", used: "one of the two engines that dreamed the clips" },
  { name: "Runway Gen-4.5", by: "Runway", licence: "via its API", used: "the other engine" },
];
export const NON_COMMERCIAL = "This page is non-commercial.";

/** Calls 16 and 24, and MODELS.md section 2: every picture drawn from the real depth (the real pane, the heat, the map of where mono
 *  depth errs, the relief and the plan view) is derived from Stereo Anywhere's output, so it carries its licence. (Open3D is not used: call 24.) */
export const DERIVED_VISUALS =
  "The real pane, the heat, the map of where mono depth errs, the relief and the plan view are drawn from depth computed with Stereo Anywhere (University of Bologna, CVPR 2025; CC BY-NC-SA 4.0) on top of Depth Anything V2 (HKU and TikTok; Large weights CC BY-NC 4.0). These derived pictures are shared under CC BY-NC-SA 4.0, for non-commercial use.";

/** Clearance 6.1: the CC licences above cover the dataset and the pictures drawn from the real depth, not the engines' output. Runway's
 *  terms section 5(viii) bars permitting a third party to use outputs to build competing products, so no open licence is put on a
 *  Runway clip or frame (P02's clearance rule); Wan 2.2's output is kept out the same way, for one clear line. */
export const GENERATED =
  "The generated clips (Runway Gen-4.5 and Wan 2.2), including the generated frames under the heat, are the engines' output and are not under these licences.";
