import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ClipNotes, Credits, PlainWordsMount, Statement } from "./Below";
import { notesFor } from "./notes";
import { DATASET, DERIVED_VISUALS, GENERATED, MODELS } from "./credits";
import { HOW_TO_READ, wallTestLimit, RELIEF_COLOUR, RELIEF_NO_WEBGL, RELIEF_NOTE, RELIEF_OUTLINE, RELIEF_STILL_NOTE, STATEMENT, WALL_TEST_LIMIT } from "./text";
import { parseClips } from "../data/load";
import { readFixtureJson } from "../test/fixtureMedia";

afterEach(cleanup);
const doc = parseClips(readFixtureJson("clips.json"));
const [dive, pellets, lost, calm] = doc.clips;
const air = doc.clips.find((c) => c.clip === "air__wan22__N__5s")!;

describe("the words below the fold", () => {
  it("the statement says the unit once in full and never millimetres as a unit", () => {
    expect(STATEMENT.join(" ")).toContain("uncorrected stereo units (su)");
    expect(STATEMENT.join(" ")).toContain("grey is where no real camera ever looked");
    expect(STATEMENT.join(" ")).not.toMatch(/\bmm\b/);
  });
  it("says what V is: the rebuilt tank's coverage, leaving out a tracked moving object", () => {
    const v = HOW_TO_READ.find((r) => r.term === "V")!.text;
    expect(v).toContain("leaving out any tracked moving object");
    expect(v).not.toMatch(/a real camera has seen what the dream/);
  });
  it("holds no digit except the two thresholds, which it takes from the constants", () => {
    const all = [...STATEMENT, ...HOW_TO_READ.map((r) => r.text), WALL_TEST_LIMIT, RELIEF_NOTE, RELIEF_STILL_NOTE, RELIEF_NO_WEBGL].join(" ");
    expect(all.match(/\d+(\.\d+)?/g)!.sort()).toEqual(["1", "3", "3", "3"].sort());
  });
  it("the relief says first that its colour is the gap as placed and not the heat, and that a tracked object is not outlined", () => {
    expect(RELIEF_NOTE.startsWith("Colour: the gap as placed, not the heat.")).toBe(true);
    expect(RELIEF_NOTE).toContain(RELIEF_OUTLINE);
    expect(RELIEF_COLOUR).toBe("Colour: the gap as placed, not the heat.");
  });
  it("the wall test's limit is said plainly, in the statement", () => {
    render(<Statement />);
    expect(screen.getByText(WALL_TEST_LIMIT)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "About this measure" }).closest("section")!.id).toBe("statement");
  });
  it("Air has no far wall (call 28): with an Air clip the statement says the far end as measured", () => {
    expect(WALL_TEST_LIMIT).toBe(wallTestLimit("freshwater"));
    render(<Statement condition="air" />);
    expect(screen.getByText(wallTestLimit("air"))).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/far wall/);
  });
});

describe("per-clip notes", () => {
  it("air Wan N carries the mask note, with the loss frame from the data", () => {
    const n = notesFor(air).find((x) => x.id === "air-wan-n-mask")!;
    expect(n.text.startsWith("The tracked outline starts on a dark flash that later resolves into the military tank (the vehicle) the dream invents.")).toBe(true);
    expect(n.text).toMatch(/left exactly as the tracker made it/);
    expect(n.text, "the loss is said once, by the lost note").not.toMatch(/lost|\d/);
    expect(notesFor(air).find((x) => x.id === "lost")!.text).toContain(`frame ${air.lost_from}`);
    expect(notesFor(dive).some((x) => x.id === "air-wan-n-mask")).toBe(false);
  });
  it("a capped clip says where and how far it is trusted, from the data", () => {
    const n = notesFor(pellets).find((x) => x.id === "cap")!;
    expect(n.text).toContain(`${pellets.trusted_travel_su} su`);
    expect(n.text).toContain(`frame ${pellets.unverifiable_from}`);
  });
  it("a lost path, a tracked object and saltwater are each noted (the saltwater note is not shown on pellets, which stop at their cap long before); a calm air clip has only the limit of V", () => {
    expect(notesFor(lost).some((x) => x.id === "lost")).toBe(true);
    expect(notesFor(air).some((x) => x.id === "tracked")).toBe(true);
    expect(notesFor(pellets).some((x) => x.id === "saltwater")).toBe(false);
    expect(notesFor({ ...calm, condition: "saltwater" }).some((x) => x.id === "saltwater")).toBe(true);
    const text = notesFor(lost).find((x) => x.id === "lost")!.text;
    expect(text).toBe(`The camera path was lost at frame ${lost.unverifiable_from}. It is never extrapolated, so nothing from there on is measured.`);
    expect(text.match(/lost/g)).toHaveLength(1);
    expect(notesFor(calm).map((x) => x.id)).toEqual(["v-limit"]);
    expect(notesFor(calm).find((x) => x.id === "v-limit")!.text).toContain("goes through the far end as measured");   // calm is an Air clip
    expect(notesFor(dive).find((x) => x.id === "v-limit")!.text).toContain("goes through the far wall");
  });
  it("the note texts hold no hand-typed figure", () => {
    for (const c of doc.clips) for (const n of notesFor(c)) {
      const withoutData = n.text.replaceAll(String(c.lost_from), "").replaceAll(String(c.unverifiable_from), "").replaceAll(String(Math.round(c.trusted_travel_su ?? NaN)), "");
      expect(withoutData, `${c.clip} ${n.id}`).not.toMatch(/\d/);
    }
  });
  it("shows the prompt, the seed and which files are the engine's own", () => {
    render(<ClipNotes clip={dive} />);
    expect(screen.getByText(`“${dive.prompt_text}”`)).toBeTruthy();
    expect(screen.getByText(String(dive.seed))).toBeTruthy();
    expect(document.body.textContent).toContain(dive.provenance.source_sha256);
    expect(document.body.textContent).toMatch(/byte for byte/);
  });
});

describe("credits", () => {
  it("name the dataset, its licence and DOI, the camera, and every model with its licence", () => {
    render(<Credits />);
    const t = document.body.textContent!;
    expect(DATASET.doi).toBe("10.5281/zenodo.16753748");
    expect(t).toContain("CC BY 4.0");
    expect(t).not.toContain("CC-BY");
    expect(t).toContain("ZED Mini");
    expect(t).toContain("10.5281/zenodo.16753748");
    for (const m of MODELS) { expect(t).toContain(m.name); expect(t).toContain(m.licence); }
    expect(t).not.toMatch(/Open3D/);                                       // not used (call 24)
    expect(screen.getByRole("link", { name: /10\.5281\/zenodo\.16753748/ }).getAttribute("href")).toBe("https://doi.org/10.5281/zenodo.16753748");
  });
  it("label the derived disparity pictures CC BY-NC-SA 4.0 and credit Stereo Anywhere and Depth Anything V2 (call 16, MODELS.md section 2)", () => {
    render(<Credits />);
    expect(DERIVED_VISUALS).toMatch(/^The real pane, the heat, the map of where mono depth errs, the relief and the plan view are drawn from depth computed with Stereo Anywhere/);
    expect(DERIVED_VISUALS).toMatch(/Stereo Anywhere \(University of Bologna, CVPR 2025; CC BY-NC-SA 4\.0\)/);
    expect(DERIVED_VISUALS).toMatch(/Depth Anything V2 \(HKU and TikTok; Large weights CC BY-NC 4\.0\)/);
    expect(DERIVED_VISUALS).toMatch(/shared under CC BY-NC-SA 4\.0/);
    expect(document.body.textContent).toContain(DERIVED_VISUALS);
  });
  it("carry the dataset's citation as Zenodo's own record gives it (clearance 6.1; copied from zenodo.org/api/records/16753748, APA)", () => {
    render(<Credits />);
    const zenodo = "Smiles, A., Farkhatdinov, I., & Oh, C. (2025). UW-TransStereo: Underwater Stereo Vision Dataset for Transparent Object Detection & Ranging [Dataset]. Zenodo. RiTA 2025, King's College London. https://doi.org/10.5281/zenodo.16753748";
    expect(DATASET.citation).toBe(zenodo);
    expect(document.body.textContent).toContain(zenodo);
  });
  it("link each Creative Commons licence they name to its text (CC 4.0 section 3(a)(1)(C))", () => {
    render(<Credits />);
    const href = (name: string) => screen.getByRole("link", { name: new RegExp(`^${name.replace(/[.]/g, "\\.")}( licence)?$`) }).getAttribute("href");
    expect(href("CC BY 4.0")).toBe("https://creativecommons.org/licenses/by/4.0/");
    expect(href("CC BY-NC-SA 4.0")).toBe("https://creativecommons.org/licenses/by-nc-sa/4.0/");
    expect(href("CC BY-NC 4.0")).toBe("https://creativecommons.org/licenses/by-nc/4.0/");
  });
  it("keep the generated clips and frames out of the CC licences (Runway's terms section 5(viii); P02's clearance rule)", () => {
    render(<Credits />);
    expect(GENERATED).toMatch(/generated clips/);
    expect(GENERATED).toMatch(/Runway Gen-4\.5 and Wan 2\.2/);
    expect(GENERATED).toMatch(/not under these licences/);
    expect(document.body.textContent).toContain(GENERATED);
  });
  it("say the page is non-commercial", () => {
    render(<Credits />);
    expect(document.body.textContent).toContain("non-commercial");
  });
});

describe("plain-words mount points", () => {
  it("render empty slots that task 4.4 fills", () => {
    const { container } = render(<><PlainWordsMount slot="invite" /><PlainWordsMount slot="chapter-1" /></>);
    expect([...container.querySelectorAll("[data-plain-words]")].map((e) => e.getAttribute("data-plain-words"))).toEqual(["invite", "chapter-1"]);
    expect(container.textContent).toBe("");
  });
});
