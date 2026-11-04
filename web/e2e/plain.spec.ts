// The plain-words layer on the real page (src/plainwords/; the hub's docs/plain-words.md), at 1440 and 390, light and dark: the invite
// and the switch, a link that opens it, the trail through the three bands, focus that follows the reader, AA contrast, every control
// reachable by keyboard, nothing over the media, no overflow at 390 or at 200 % text, and the choice carried on studio links.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { CALM, goldPixels, needAssets, open, watchConsole } from "./helpers";
import { CHAPTERS, NOTES } from "../src/plainwords/words";

test.beforeEach(async ({ page }) => { await needAssets(page); });

const isPhone = (page: Page) => (page.viewportSize()?.width ?? 0) < 761;
const band = (page: Page, n: number) => page.locator(`#${CHAPTERS[n - 1].id}`);
const layer = ".pw-invite, .pw-band, .pw-note";

test("until asked: only the invite, no band and no note; the invite turns it on, focus goes to the first band, and a reload keeps it", async ({ page }) => {
  const problems = watchConsole(page);
  await open(page);
  await expect(page.locator(".pw-invite")).toContainText("Read it in plain words");
  await expect(page.locator(".pw-band, .pw-note")).toHaveCount(0);
  await page.getByRole("button", { name: "Read it in plain words" }).click();
  await expect(page.locator(".pw-band")).toHaveCount(3);
  await expect(band(page, 1)).toBeFocused();
  await expect(page.locator(".pw-note")).toHaveCount(Object.keys(NOTES).length);
  await expect(page.locator("h1")).toHaveCount(1);
  await page.reload();
  await expect(page.locator(".pw-band")).toHaveCount(3);
  expect(problems).toEqual([]);
});

test("?plain=1 opens it and ?plain=0 closes it; Hide drops ?plain= (keeping the clip), hands focus to the switch, and the switch brings it back", async ({ page }) => {
  await page.goto("/?plain=1&clip=air__gen45__D__5s&f=10");
  await expect(page.locator(".pw-band")).toHaveCount(3);
  await page.locator(`${"#" + CHAPTERS[1].id} .pw-quiet`).click();
  await expect(page.locator(layer)).toHaveCount(0);
  expect(new URL(page.url()).searchParams.get("plain")).toBeNull();
  expect(new URL(page.url()).searchParams.get("clip")).toBe("air__gen45__D__5s");
  await expect(isPhone(page) ? page.getByRole("button", { name: "Menu" }) : page.getByRole("button", { name: "Plain words" })).toBeFocused();
  await page.reload();
  await expect(page.locator(layer)).toHaveCount(0);
  if (isPhone(page)) await page.getByRole("button", { name: "Menu" }).click();
  const sw = page.getByRole("button", { name: "Plain words" });
  await expect(sw).toHaveAttribute("aria-pressed", "false");
  await sw.click();
  await expect(page.locator(".pw-band")).toHaveCount(3);
  await expect(band(page, 1)).toBeFocused();
  await page.goto("/?plain=0");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator(layer)).toHaveCount(0);
});

test("Not now puts the invite away for this visit; the next visit asks again", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Not now" }).click();
  await expect(page.locator(".pw-invite")).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator(".pw-invite")).toHaveCount(0);
  await page.evaluate(() => sessionStorage.clear());
  await page.reload();
  await expect(page.locator(".pw-invite")).toBeVisible();
});

test("the trail: chapter 1 above the stage, 2 above the evidence row, 3 above the statement; Next scrolls to the next band and focuses it", async ({ page }) => {
  await page.goto("/?plain=1");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const y = (sel: string) => page.locator(sel).first().evaluate((e) => e.getBoundingClientRect().top + scrollY);
  expect(await y(`#${CHAPTERS[0].id}`)).toBeLessThan(await y(".stage"));
  expect(await y(".stage")).toBeLessThan(await y(`#${CHAPTERS[1].id}`));
  expect(await y(`#${CHAPTERS[1].id}`)).toBeLessThan(await y(".evidence"));
  expect(await y(".evidence")).toBeLessThan(await y(`#${CHAPTERS[2].id}`));
  expect(await y(`#${CHAPTERS[2].id}`)).toBeLessThan(await y("#statement"));
  for (let n = 1; n <= 3; n++) {
    await expect(band(page, n).locator(".pw-title")).toHaveText(CHAPTERS[n - 1].title);
    await expect(band(page, n)).toContainText(`chapter ${n} of 3`);
    const map = band(page, n).locator(".pw-map");
    if (!isPhone(page) && (page.viewportSize()!.width >= 1280)) {
      await expect(map.getByRole("link")).toHaveText(CHAPTERS.map((c, k) => `${k + 1}${c.title}`));
      await expect(map.locator('[aria-current="step"]')).toContainText(CHAPTERS[n - 1].title);
    }
    const next = band(page, n).locator(".pw-next");
    await expect(next).toContainText(n < 3 ? `Next: ${CHAPTERS[n].title}` : "Back to the start");
    await next.click();
    const to = n < 3 ? n + 1 : 1;
    await expect(band(page, to)).toBeFocused();
    await expect.poll(() => band(page, to).evaluate((e) => Math.round(e.getBoundingClientRect().top)), { timeout: 5000 })
      .toBeGreaterThanOrEqual(48);                                                // under the sticky bar, not behind it
    await expect.poll(() => band(page, to).evaluate((e) => e.getBoundingClientRect().top < innerHeight / 2)).toBe(true);
  }
  expect(new URL(page.url()).hash).toBe("");
});

test("blue pencil never sits over the media, and gold still means only D above 3", async ({ page }) => {
  await page.goto(`/?plain=1&clip=${CALM}&f=60`);
  await expect(page.locator(".pw-band")).toHaveCount(3);
  await page.locator(".relief").scrollIntoViewIfNeeded();
  await expect(page.locator(".relief-canvas, .relief-still").first()).toBeVisible({ timeout: 15_000 });
  const overlaps = await page.evaluate((sel) => {
    const media = [...document.querySelectorAll("video:not([hidden]), .pane-frame, .relief-frame, .plan svg, .floor-thumb img, .start-fig img, .track-box")]
      .map((e) => e.getBoundingClientRect());
    return [...document.querySelectorAll(sel)].flatMap((p) => {
      const r = p.getBoundingClientRect();
      return media.some((m) => r.left < m.right - 0.5 && m.left < r.right - 0.5 && r.top < m.bottom - 0.5 && m.top < r.bottom - 0.5) ? [(p as HTMLElement).dataset.note ?? p.className] : [];
    });
  }, layer);
  expect(overlaps).toEqual([]);
  expect(await goldPixels(page), "no gold on a clip that never passes 3, with the layer on").toBe(0);
});

test("AA contrast on the layer, on paper and on the stage", async ({ page }) => {
  await page.goto("/?plain=1");
  await expect(page.locator(".pw-band")).toHaveCount(3);
  const r = await new AxeBuilder({ page }).include(".pw-band").include(".pw-note").include(".plain-btn").withRules(["color-contrast"]).analyze();
  expect(r.violations.flatMap((v) => v.nodes.map((n) => `${n.target.join(" ")}: ${n.failureSummary}`))).toEqual([]);
  expect(r.passes.length + r.incomplete.length).toBeGreaterThan(0);
  await page.evaluate(() => localStorage.removeItem("dt-plain"));                    // a first visit: the invite
  await page.goto("/");
  await expect(page.locator(".pw-invite")).toBeVisible();
  const inv = await new AxeBuilder({ page }).include(".pw-invite").withRules(["color-contrast"]).analyze();
  expect(inv.violations).toEqual([]);
});

test("every control in the layer is reachable with Tab, in reading order", async ({ page }) => {
  await page.goto("/?plain=1");
  await expect(page.locator(".pw-band")).toHaveCount(3);
  const want = await page.locator(".pw-band a:visible, .pw-band button:visible").evaluateAll((els) => els.map((e) => e.textContent!.trim()));
  expect(want.length).toBeGreaterThanOrEqual(6);
  await page.locator("body").focus();
  const seen: string[] = [];
  for (let i = 0; i < 250 && seen.length < want.length; i++) {
    await page.keyboard.press("Tab");
    const t = await page.evaluate(() => (document.activeElement?.closest(".pw-band") ? document.activeElement.textContent!.trim() : null));
    if (t !== null) seen.push(t);
  }
  expect(seen).toEqual(want);
});

test("no overflow with the layer on, at this width and with text at 200 %", async ({ page }) => {
  const problems = watchConsole(page);
  await page.goto("/?plain=1");
  await expect(page.locator(".pw-band")).toHaveCount(3);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  // text-only zoom: every type token doubled (the layer's sizes all come from them), the layout's widths left as they are
  await page.addStyleTag({ content: ":root { --fs-title: 48px; --fs-section: 32px; --fs-body: 28px; --fs-small: 24px; }" });
  await page.waitForTimeout(100);
  const over = await page.locator(layer).evaluateAll((els) => els.flatMap((e) => {
    const r = e.getBoundingClientRect();
    const spill = [e, ...e.querySelectorAll("*:not(.visually-hidden)")].some((x) => (x as HTMLElement).scrollWidth > (x as HTMLElement).clientWidth + 1 && getComputedStyle(x).overflowX !== "visible");
    return r.left < -0.5 || r.right > innerWidth + 0.5 || e.scrollWidth > e.clientWidth + 1 || spill ? [(e as HTMLElement).dataset.note ?? (e as HTMLElement).id ?? e.className] : [];
  }));
  expect(over, "layer elements that overflow at 200 % text").toEqual([]);
  expect(problems).toEqual([]);
});

test("with the layer on, links into other studio sites carry ?plain=1; with it off they don't", async ({ page }) => {
  await page.goto("/?plain=1");
  await expect(page.locator(".pw-band")).toHaveCount(3);
  await page.evaluate(() => {
    const a = document.createElement("a"); a.id = "probe"; a.href = "https://studionephele.com/work"; a.textContent = "work";
    document.querySelector("main")!.append(a);
  });
  await expect(page.locator("#probe")).toHaveAttribute("href", "https://studionephele.com/work?plain=1");
  await page.locator(`#${CHAPTERS[0].id} .pw-quiet`).click();
  await expect(page.locator("#probe")).toHaveAttribute("href", "https://studionephele.com/work");
});
