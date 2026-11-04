import { expect, test } from "@playwright/test";
import { needAssets } from "./helpers";

// Clearance (task 6.1): the page's live words, every real clip, with the plain-words layer on and off, hold the card's publication
// rules. Nothing from unpublished research (no contour estimator, no refraction fit, no error figure, no venue), and
// millimetres appear only in the statement's "never millimetres". The hub's scan-identifiers.sh covers names and identifiers; it is
// not repeated here, so that no forbidden name is ever written into this repo.
// Venue names are not listed in this public repo: set DIVETWIN_EXTRA_BANNED to a "|"-joined regex to check them locally.
const EXTRA = process.env.DIVETWIN_EXTRA_BANNED;
const BANNED: RegExp[] = [/contour/i, /refract/i, /n_eff/i, /\bMAE\b/, /under review/i, /\bmm\b/, /\branging error/i, ...(EXTRA ? [new RegExp(EXTRA, "i")] : [])];

const words = async (page: import("@playwright/test").Page) =>
  page.evaluate(() => {
    const attrs = [...document.querySelectorAll("[alt], [aria-label], [title]")].flatMap((e) =>
      ["alt", "aria-label", "title"].map((a) => e.getAttribute(a) ?? ""));
    return [document.title, document.body.innerText, ...attrs].join("\n");
  });

test("every clip's page words hold the clearance rules, with plain words on and off", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop-light", "the words are the same at every size and scheme; one project reads them");
  test.setTimeout(240_000);
  await needAssets(page);
  const doc = await (await page.request.get("/media/clips.json")).json() as { clips: { clip: string }[] };
  expect(doc.clips).toHaveLength(35);
  for (const { clip } of doc.clips) {
    for (const plain of ["1", "0"]) {
      await page.goto(`/?clip=${clip}&plain=${plain}`);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.locator("#credits-h")).toBeAttached();
      const text = await words(page);
      for (const rx of BANNED) expect(text, `${clip} plain=${plain}: ${rx}`).not.toMatch(rx);
      const mm = text.match(/millimet\w*/gi) ?? [];
      expect(mm, `${clip} plain=${plain}: millimetres outside the statement`).toEqual(["millimetres"]);
      expect(text).toContain("never millimetres");
      expect(text).toContain("ZED Mini");
      expect(text).toContain("10.5281/zenodo.16753748");
    }
  }
});
