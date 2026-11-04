// The findings band (hub call 92), at 1440 and 390, light and dark (the four projects), against the real runs/assets: the answer, the
// tally computed from clips.json, the two surprises, each count by keyboard, the fold at 1440 x 900, axe and no gold.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { decode } from "fast-png";
import { DEFAULT, layoutProblems, needAssets, open, watchConsole } from "./helpers";

test.beforeEach(async ({ page }) => { await needAssets(page); });

/** The tally from the served clips.json by the raw arrays (not the page's code): a departure; above 3 without one; ran out or never
 *  measured; the rest. Equals THESIS.md's 3, 2, 5 and 25 on the real file, which the last line also holds. */
async function expectedTally(page: Page) {
  const doc = await (await page.request.get("/media/clips.json")).json() as { clips: { clip: string; D: (number | null)[]; first_D3: number | null; unverifiable_from: number | null }[] };
  const kind = (c: (typeof doc.clips)[number]) => {
    const m = c.D.map((d, f) => (c.unverifiable_from !== null && f >= c.unverifiable_from ? null : d));
    if (m.every((d) => d === null)) return "unchecked";
    if (c.first_D3 !== null) return "departs";
    if (m.some((d) => d !== null && d > 3)) return "spikes";
    return c.unverifiable_from !== null ? "unchecked" : "under";
  };
  const ids: Record<string, string[]> = { departs: [], spikes: [], under: [], unchecked: [] };
  for (const c of doc.clips) ids[kind(c)].push(c.clip);
  expect(Object.values(ids).map((v) => v.length), "THESIS.md: 3 leave for good, 2 spike, 25 stay under, 5 run out first").toEqual([3, 2, 25, 5]);
  return { total: doc.clips.length, ids };
}

const LABELS: [string, RegExp][] = [
  ["departs", /^3 leave the tank for good$/], ["spikes", /^2 spike past 3$/], ["under", /^25 stay under 3$/], ["unchecked", /^5 can't be checked to the end$/],
];

test("the band: the answer, the tally from clips.json and the two surprises, between the title row and the stage, inside the page, never gold", async ({ page }) => {
  const problems = watchConsole(page);
  await open(page);
  const { total } = await expectedTally(page);
  const band = page.locator(".band");
  await expect(band.locator(".band-answer")).toHaveText("A dream can be checked against the real tank frame by frame, until it leaves what was measured.");
  const counts = band.getByRole("group", { name: `The ${total} clips, by their finding line` }).getByRole("button");
  await expect(counts).toHaveCount(4);
  for (const [i, [, re]] of LABELS.entries()) await expect(counts.nth(i)).toHaveText(re);
  await expect(band.locator(".surprises li")).toHaveText([
    "Dreams open the tank up: in every clip past 3, the invented space reads farther than the real tank.",
    "Only D sees a dream leave: the Gen-4.5 clips past 3 keep V at 1.00; the rebuilt tank still covers the frame.",
  ]);
  // in the reading order: the title row, the band, the stage
  const tops = await page.evaluate(() => [".title-row", ".band", ".stage"].map((s) => { const r = document.querySelector(s)!.getBoundingClientRect(); return [r.top, r.bottom]; }));
  expect(tops[1][0]).toBeGreaterThanOrEqual(tops[0][1]);
  expect(tops[2][0]).toBeGreaterThanOrEqual(tops[1][1]);
  expect(await page.evaluate(() => document.querySelector("h1")!.compareDocumentPosition(document.querySelector(".band")!) & Node.DOCUMENT_POSITION_FOLLOWING)).toBeTruthy();
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  expect(await layoutProblems(page)).toEqual([]);
  // no pixel of the band is the page's --gold (gold is D above 3; the band is never it, whatever the cursor shows)
  const gold = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--gold").trim());
  const want = [1, 3, 5].map((i) => parseInt(gold.slice(i, i + 2), 16));
  const png = decode(await band.screenshot());
  let n = 0;
  for (let i = 0; i < png.data.length; i += png.channels) if (want.every((w, k) => Math.abs(png.data[i + k] - w) <= 2)) n++;
  expect(n, "gold pixels in the band").toBe(0);
  expect(problems).toEqual([]);
});

test("at 1440 the band is two lines (the answer with the tally, then the surprises side by side); on a phone it sits under the title row, before the stage", async ({ page }, info) => {
  await open(page);
  const box = (await page.locator(".band").boundingBox())!;
  const line = await page.locator(".band-answer").evaluate((e) => parseFloat(getComputedStyle(e).lineHeight));
  if (info.project.name.startsWith("desktop")) {
    expect(box.height, "two lines").toBeLessThan(2 * line + 8);
    const [a, t] = await page.locator(".band-answer, .tally").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().top));
    expect(Math.abs(a - t), "the tally on the answer's line").toBeLessThan(4);
    const s = await page.locator(".surprises li").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().top));
    expect(Math.abs(s[0] - s[1]), "the surprises side by side").toBeLessThan(1);
  } else {
    // a phone: each count is a 44 px touch target
    for (const h of await page.locator(".tally-btn").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height))) expect(h).toBeGreaterThanOrEqual(44);
    const picker = (await page.locator(".picker").boundingBox())!, stage = (await page.locator(".stage").boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(picker.y + picker.height);
    expect(box.y + box.height).toBeLessThanOrEqual(stage.y);
  }
});

for (const [kind, re] of LABELS) {
  test(`by keyboard: "${re.source.slice(1, -1)}" shows exactly its clips in the table, focus lands on the line that says so, and Show all brings every clip back`, async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto(`/?clip=${DEFAULT}&plain=0`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const { total, ids } = await expectedTally(page);
    // the counts follow the picker in Tab order: from the picker's last control, Tab reaches the first count, then each in turn
    await page.locator(".picker").locator("input:checked, select").last().focus();
    await page.keyboard.press("Tab");
    await expect(page.locator(".band .tally-btn").first()).toBeFocused();
    const index = LABELS.findIndex(([k]) => k === kind);
    for (let i = 0; i < index; i++) await page.keyboard.press("Tab");
    const btn = page.locator(".band .tally-btn", { hasText: re });
    await expect(btn).toBeFocused();
    await expect(btn).toHaveAccessibleName(new RegExp(`${re.source.slice(1, -1)}: show them in the clip table$`));
    await page.keyboard.press("Enter");
    const filter = page.locator(".table-filter");
    await expect(filter).toBeFocused();
    // in view, and not under the sticky bar: the table's heading and the line are both readable once the scroll settles
    // (judged only once the page has stopped moving: a smooth scroll passes through a good position on its way to a bad one)
    const settled = async () => page.evaluate(async () => {
      const y0 = scrollY;
      await new Promise((r) => setTimeout(r, 250));
      if (scrollY !== y0) return "moving";
      const bar = document.querySelector(".bar")!.getBoundingClientRect(), h = document.getElementById("table-h")!.getBoundingClientRect(), f = document.querySelector(".table-filter")!.getBoundingClientRect();
      return h.top >= bar.bottom && f.bottom <= window.innerHeight ? "readable" : `under the bar or off screen (heading top ${Math.round(h.top)}, bar bottom ${Math.round(bar.bottom)})`;
    });
    await expect.poll(settled, { timeout: 8000 }).not.toBe("moving");
    expect(await settled()).toBe("readable");
    const n = ids[kind].length;
    await expect(filter).toContainText(`Showing the ${n} ${n === 1 ? "clip" : "clips"} that`);
    const rows = page.locator(".clip-table tbody tr");
    await expect(rows).toHaveCount(n);
    const shown = await rows.evaluateAll((trs) => trs.map((tr) => tr.querySelector(".row-btn")!.getAttribute("aria-label")));
    const titles = await page.evaluate(async (want) => {
      const doc = await (await fetch("/media/clips.json")).json();
      const name: Record<string, string> = { air: "Air", freshwater: "Freshwater", "freshwater-basicEnhance": "Freshwater, enhanced", saltwater: "Saltwater", "saltwater-pellets": "Saltwater, pellets" };
      const eng: Record<string, string> = { gen45: "Gen-4.5", wan22: "Wan 2.2" };
      return want.map((id: string) => { const c = doc.clips.find((x: { clip: string }) => x.clip === id); return `${name[c.condition]} · ${eng[c.engine]} · prompt ${c.prompt} · ${c.seconds} s`; });
    }, ids[kind]);
    expect(shown).toEqual(titles);
    // Tab goes on to "Show all", which brings every clip back
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: `Show all ${total}` })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(rows).toHaveCount(total);
    await expect(filter).toHaveCount(0);
    expect(problems).toEqual([]);
  });
}

test("axe: with a count's clips shown in the table, no violation of any impact", async ({ page }) => {
  await page.goto(`/?clip=${DEFAULT}&plain=0`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.locator(".band .tally-btn").nth(1).click();
  await expect(page.locator(".table-filter")).toBeFocused();
  const res = await new AxeBuilder({ page }).analyze();
  expect(res.violations.map((v) => `${v.id}:${v.impact}:${v.nodes.map((x) => x.target.join(" ")).slice(0, 3).join(" | ")}`)).toEqual([]);
});
