// Task 4.6, break-ui: the worst realistic data on the real page (real media, real layout), at 1440 and 390, light and dark. The data is
// changed at the boundary only: the page's own fetch of clips.json and path.json is answered with a mutated copy (src/test/worst.ts), and
// the relief atlas and floor preview are answered 404. Nothing in the app is edited to produce a break. The text side of each case is
// also a Vitest (src/test/worst.test.tsx).
import { expect, test, type Page } from "@playwright/test";
import { dead, LONG_NAME_60, longName, offScale, type DeadReason } from "../src/test/worst";
import { DEFAULT, layoutProblems, needAssets, open, readable, sliderValue, waitForFrame, watchConsole } from "./helpers";

test.beforeEach(async ({ page }) => { await needAssets(page); });

type J = any;
interface Faults { doc?: (d: J) => J; paths?: Record<string, (p: J, d: J) => { doc?: J; path: J }>; missing?: RegExp[] }

/** Answer the page's fetches with the faulted copy: clips.json mutated, a clip's path.json mutated, some files 404. */
async function serve(page: Page, f: Faults) {
  let doc: J = null;
  const clips = async () => { if (!doc) { const r = await page.request.get("/media/clips.json"); doc = await r.json(); if (f.doc) doc = f.doc(doc); } return doc; };
  await page.route("**/media/clips.json", async (route) => route.fulfill({ json: await clips() }));
  for (const [id, fn] of Object.entries(f.paths ?? {})) {
    await page.route(`**/media/clips/${id}/path.json`, async (route) => {
      const real = await (await page.request.get(`/media/clips/${id}/path.json`)).json();
      route.fulfill({ json: fn(real, await clips()).path });
    });
  }
  for (const m of f.missing ?? []) await page.route(m, (route) => route.fulfill({ status: 404, body: "not found" }));
}

const noBadWords = (text: string) => expect(text).not.toMatch(/NaN|undefined|\bnull\b|Infinity|\b0\.00\b/);

test("a D off the scale (40): the curve stops at its top edge, the lead figure and the table say 40.00 and fit, and gold is gold", async ({ page }, info) => {
  const problems = watchConsole(page);
  await serve(page, { doc: (d) => offScale(d, DEFAULT, 40) });
  await open(page, DEFAULT, 110);
  expect(await layoutProblems(page)).toEqual([]);
  const lead = page.locator(".numbers .lead");
  await expect(lead).toHaveText("40.00");
  const [lb, nb] = await Promise.all([lead.boundingBox(), page.locator(".numbers").boundingBox()]);
  expect(lb!.x + lb!.width).toBeLessThanOrEqual(nb!.x + nb!.width);
  await expect(page.getByRole("slider", { name: "Frame" })).toHaveAttribute("aria-valuetext", /D 40\.00/);
  // the curve never leaves its 48 px track: every point of every gold run is inside the SVG
  const out = await page.locator(".tracks").evaluate((svg) => {
    const h = Number(svg.getAttribute("height"));
    return [...svg.querySelectorAll<SVGPathElement>(".curve")].flatMap((p) => (p.getAttribute("d") ?? "").match(/,(-?[\d.]+)/g) ?? []).map((s) => Number(s.slice(1))).filter((y) => y < 0 || y > h);
  });
  expect(out).toEqual([]);
  await page.locator(".clip-table").scrollIntoViewIfNeeded();
  await expect(page.locator(".clip-table tbody tr.is-active")).toContainText("40.00");
  expect(await layoutProblems(page)).toEqual([]);
  noBadWords((await readable(page)).replace("40.00", ""));
  await page.screenshot({ path: `${process.env.VERIFY_SHOTS ?? "test-results"}/worst-offscale-${info.project.name}.png`, fullPage: false });
  expect(problems).toEqual([]);
});

test("a recording name of 60 characters: whole in the title, the picker and the table, nothing past the edge, and choosing it works", async ({ page }, info) => {
  expect(LONG_NAME_60).toHaveLength(60);
  const problems = watchConsole(page);
  await serve(page, { doc: (d) => longName(d, "freshwater-basicEnhance", LONG_NAME_60) });
  await open(page, DEFAULT);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(`${LONG_NAME_60} · Gen-4.5 · prompt N · 5 s`);
  expect(await layoutProblems(page)).toEqual([]);
  // the picker: pick another recording and then the long one again, by pointer and by keyboard
  const phone = info.project.name.startsWith("phone");
  if (phone) await page.getByLabel("Recording").selectOption({ label: "Air" });
  else await page.getByRole("radio", { name: "Air" }).check({ force: true });
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Air");
  expect(await layoutProblems(page)).toEqual([]);
  if (phone) await page.getByLabel("Recording").selectOption({ label: LONG_NAME_60 });
  else { await page.getByRole("radio", { name: LONG_NAME_60 }).focus(); await page.keyboard.press("Space"); }
  await expect(page.getByRole("heading", { level: 1 })).toContainText(LONG_NAME_60);
  // the first screen still holds the stage and the scrubber (a long title must not push them off it)
  const scrub = await page.getByRole("slider", { name: "Frame" }).boundingBox();
  expect(scrub!.y + scrub!.height).toBeLessThanOrEqual(info.project.name.startsWith("phone") ? 2400 : 900);
  await page.locator(".clip-table").scrollIntoViewIfNeeded();
  await expect(page.locator(".clip-table tbody tr.is-active .row-btn")).toHaveText(LONG_NAME_60);
  expect(await layoutProblems(page)).toEqual([]);
  noBadWords(await readable(page));
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: `${process.env.VERIFY_SHOTS ?? "test-results"}/worst-longname-${info.project.name}.png`, fullPage: false });
  expect(problems).toEqual([]);
});

test("a missing relief atlas and a missing floor preview: each panel says so in words, the rest of the page works", async ({ page }, info) => {
  const problems: string[] = [];
  page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !/Failed to load resource.*404|THREE\.Clock|GL Driver Message|GPU stall/.test(m.text())) problems.push(m.text()); });
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  await serve(page, { missing: [/\/relief\.png$/, /\/tank_relief\.png$/, /\/floor_preview\.jpg$/] });
  await page.goto(`/?clip=${DEFAULT}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator("[data-floor-map] .floor-missing")).toContainText("could not be loaded");
  await expect(page.locator("[data-floor-map] figcaption")).toContainText("where mono depth already errs");   // the key stays
  await page.locator(".relief").scrollIntoViewIfNeeded();
  await expect(page.locator(".relief [role=alert]")).toContainText("The depth atlas could not be loaded.");
  expect(await layoutProblems(page)).toEqual([]);
  // the rest still works: scrub with the keyboard, and the numbers follow
  await page.getByRole("slider", { name: "Frame" }).focus();
  await page.keyboard.press("Home");
  expect(await sliderValue(page)).toBe(0);
  await waitForFrame(page, 0);
  await expect(page.locator(".numbers .lead")).not.toHaveText("");
  await expect(page.locator(".plan svg")).toBeVisible();
  noBadWords(await readable(page));
  await page.locator(".relief").scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${process.env.VERIFY_SHOTS ?? "test-results"}/worst-missing-${info.project.name}.png`, fullPage: false });
  expect(problems).toEqual([]);
});

for (const [id, reason] of [["saltwater__gen45__B__5s", "travel cap"], ["freshwater__wan22__D__5s", "path lost"]] as [string, DeadReason][]) {
  test(`a clip unverifiable from frame 0 (${reason}): no number, never 0.00, every pane says why, and every control still works`, async ({ page }, info) => {
    const problems = watchConsole(page);
    await serve(page, { doc: (d) => dead(d, { x: [], z: [], yaw_deg: [] }, id, reason).doc, paths: { [id]: (p, d) => dead(d, p, id, reason) } });
    await open(page, id);
    await expect(page.locator(".finding")).toHaveText(/^Verification ran out at frame 0 \(0\.0 s\): /);
    await expect(page.locator(".finding")).toContainText("no frame could be measured");
    await expect(page.locator(".numbers .lead")).toHaveText("unverifiable");
    await expect(page.locator('[data-pane="real"] .pane-notice')).toContainText("From frame 0, nothing here can be checked");
    await expect(page.locator('[data-pane="real"] .pane-notice button')).toHaveCount(0);       // there is no checked frame to go back to
    await expect(page.locator(".plan svg")).toBeVisible();
    await expect(page.locator(".plan svg .cursor")).toHaveCount(0);                              // no path, so no cursor and no stop marker
    await expect(page.locator(".plan svg .stop")).toHaveCount(0);
    await expect(page.getByRole("slider", { name: "Frame" })).toHaveAttribute("aria-valuetext", "f0 · 0.00 s, D unverifiable, V unverifiable");
    expect(await sliderValue(page)).toBe(0);
    await page.locator(".clip-table").scrollIntoViewIfNeeded();
    const row = page.locator(".clip-table tbody tr.is-active");
    await expect(row.locator('[data-col="d5"]')).toHaveText("unverifiable");
    await expect(row.locator('[data-col="v5"]')).toHaveText("unverifiable");
    expect(await layoutProblems(page)).toEqual([]);
    noBadWords(await readable(page));
    // the controls: scrub to the end and back, play (it must run and stop by itself), the dream switch
    await page.evaluate(() => scrollTo(0, 0));
    const slider = page.getByRole("slider", { name: "Frame" });
    await slider.focus(); await page.keyboard.press("End");
    expect(await sliderValue(page)).toBe(120);
    await expect(page.locator(".numbers .lead")).toHaveText("unverifiable");
    await page.getByRole("radio", { name: "Bare" }).check({ force: true });
    await page.keyboard.press("Home");
    await page.getByRole("button", { name: "Play" }).click();
    await expect(page.getByRole("button", { name: "Play" })).toBeVisible({ timeout: 15_000 });
    noBadWords(await readable(page));
    await page.screenshot({ path: `${process.env.VERIFY_SHOTS ?? "test-results"}/worst-dead-${reason.replace(" ", "-")}-${info.project.name}.png`, fullPage: false });
    expect(problems).toEqual([]);
  });
}

test("the 10 s dive at its last frame: f240, 10.00 s, every pane on that frame, End and Play behave, nothing overflows", async ({ page }, info) => {
  const problems = watchConsole(page);
  await open(page, "air__gen45__D__10s", 240);
  await expect(page.locator(".readout")).toHaveText("f240 · 10.00 s");
  expect(await sliderValue(page)).toBe(240);
  await waitForFrame(page, 240);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Air · Gen-4.5 · prompt D · 10 s");
  expect(await layoutProblems(page)).toEqual([]);
  noBadWords(await readable(page));
  await page.keyboard.press("Escape");
  const slider = page.getByRole("slider", { name: "Frame" });
  await slider.focus();
  await page.keyboard.press("ArrowRight");                                  // past the end: stays on 240
  expect(await sliderValue(page)).toBe(240);
  await page.keyboard.press("Shift+ArrowRight");
  expect(await sliderValue(page)).toBe(240);
  await page.screenshot({ path: `${process.env.VERIFY_SHOTS ?? "test-results"}/worst-10s-last-${info.project.name}.png`, fullPage: false });
  // Play from the last frame starts again from 0 and ends on 240 by itself, paused
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible({ timeout: 20_000 });
  expect(await sliderValue(page)).toBe(240);
  await waitForFrame(page, 240);
  expect(problems).toEqual([]);
});
