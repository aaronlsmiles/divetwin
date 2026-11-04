// Task 4.6, the verify pass: every control by pointer and by keyboard, sync on a throttled CPU, axe, text at 200 %, reduced motion.
// (The worst-data trail is worst.spec.ts; the layout, plain-words and sync-at-rest checks are dive.spec.ts and plain.spec.ts.)
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { DEFAULT, layoutProblems, needAssets, open, sliderValue, waitForFrame, waitForVideos, watchConsole } from "./helpers";

test.beforeEach(async ({ page }) => { await needAssets(page); });
const phoneOnly = (info: { project: { name: string } }) => test.skip(!info.project.name.startsWith("phone"), "the phone check");
const desktopOnly = (info: { project: { name: string } }) => test.skip(!info.project.name.startsWith("desktop"), "the desktop check");

// ---------------------------------------------------------------------------------------------------------------- every control

/** What a keyboard user lands on: the focused element's name, and whether anything draws a ring (the range and the radios are
 *  invisible natives, so their ring is on the track box and the segment). */
const focusInfo = (page: Page) => page.evaluate(() => {
  const e = document.activeElement as HTMLElement | null;
  if (!e || e === document.body) return null;
  const name = e.getAttribute("aria-label") ?? (e as HTMLInputElement).labels?.[0]?.textContent ?? e.textContent ?? "";
  const rings = [e, e.closest(".seg-opt"), e.closest(".track-box")].filter((x): x is Element => !!x).map((x) => getComputedStyle(x));
  const ring = rings.some((cs) => cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 2);
  const r = e.getBoundingClientRect(), vr = (e.closest(".seg-opt") ?? e.closest(".track-box") ?? e).getBoundingClientRect();
  return { tag: e.tagName.toLowerCase(), type: (e as HTMLInputElement).type ?? "", name: name.trim().replace(/\s+/g, " ").slice(0, 60), ring, visible: (vr.width > 0 && vr.height > 0) || (r.width > 0 && r.height > 0), id: e.id };
});

test("every control in Tab order has a name, a visible ring and a place on the page; the skip links work; there is no positive tabindex", async ({ page }) => {
  const problems = watchConsole(page);
  await open(page);
  expect(await page.locator('[tabindex]:not([tabindex="-1"]):not([tabindex="0"])').count(), "a positive tabindex").toBe(0);
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  const seen: string[] = [];
  const bad: string[] = [];
  for (let i = 0; i < 160; i++) {
    await page.keyboard.press("Tab");
    const f = await focusInfo(page);
    if (!f) break;
    const label = `${f.tag}${f.type ? `:${f.type}` : ""} "${f.name}"`;
    seen.push(label);
    if (!f.name) bad.push(`${label} has no name`);
    if (!f.ring) bad.push(`${label} shows no focus ring`);
    if (!f.visible) bad.push(`${label} is not visible`);
  }
  expect(bad, "controls that fail").toEqual([]);
  expect(seen.length, "the sweep ran to the end of the page and wrapped").toBeLessThan(160);
  expect(seen[0]).toContain("Skip to the dive");
  expect(seen[1]).toContain("Skip to the scrubber");
  // the page's main controls are all in the sweep, in reading order: picker, then the stage's switch, Play and the slider, then the table
  const at = (needle: string) => seen.findIndex((s) => s.includes(needle));
  for (const n of ["Heat", "Play", "Frame"]) expect(at(n), n).toBeGreaterThan(-1);
  expect(at("Play")).toBeLessThan(at("Frame"));
  expect(at("Frame")).toBeLessThan(seen.findIndex((s) => s.includes("Recording") && s.startsWith("button")));
  // the skip links: "Skip to the scrubber" puts focus on the slider, and the arrow keys then scrub
  await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0); });
  await page.keyboard.press("Tab"); await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to the scrubber" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("slider", { name: "Frame" })).toBeFocused();
  const f0 = await sliderValue(page);
  await page.keyboard.press("ArrowLeft");
  expect(await sliderValue(page)).toBe(f0 - 1);
  expect(problems).toEqual([]);
});

test("every control by pointer: the picker, the dream switch, Play, the scrubber, the table, the theme, plain words, the menu and the links", async ({ page }, info) => {
  const problems = watchConsole(page);
  await open(page);
  const phone = info.project.name.startsWith("phone");
  // the scrubber by pointer: a click a quarter of the way along the track lands near frame 30 (the gutter on the right is not the track)
  await page.locator(".track-box").scrollIntoViewIfNeeded();
  const box = (await page.locator(".track-box").boundingBox())!;
  await page.mouse.click(box.x + box.width * 0.25, box.y + box.height / 2);
  await expect.poll(async () => { const v = await sliderValue(page); return v >= 28 && v <= 32; }).toBe(true);
  await waitForFrame(page, await sliderValue(page));
  // Play, then Pause
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Pause" }).click();
  await expect(page.getByRole("button", { name: "Play" })).toHaveAttribute("aria-pressed", "false");
  // Heat and Bare
  await page.getByRole("radio", { name: "Bare" }).check({ force: true });
  await expect(page.locator('video[data-pane-video="gen"]')).toBeVisible();
  await page.getByRole("radio", { name: "Heat" }).check({ force: true });
  await expect(page.locator('video[data-pane-video="heat"]')).toBeVisible();
  // the picker: recording, engine, prompt, and the length where a dive exists
  const pick = async (label: string, option: string) => {
    if (phone) await page.getByLabel(label, { exact: false }).first().selectOption({ label: option });
    else await page.getByRole("group", { name: "Choose a clip" }).getByRole("radio", { name: option, exact: true }).check({ force: true });
  };
  await pick("Recording", "Air");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Air");
  await pick("Engine", phone ? "Wan 2.2" : "Wan 2.2");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Wan 2.2");
  await pick("Prompt", "D");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("prompt D");
  await pick("Engine", "Gen-4.5");
  if (!phone) {
    await page.getByRole("radio", { name: "10 s" }).check({ force: true });
    await expect(page.getByRole("heading", { level: 1 })).toContainText("10 s");
  } else {
    await expect(page.getByRole("heading", { level: 1 })).toContainText("prompt D");
  }
  // the table: sort, then a row (loads the stage and scrolls back to it)
  await page.locator(".clip-table").scrollIntoViewIfNeeded();
  if (!phone) {
    const th = page.getByRole("columnheader", { name: /^Departure/ });
    await th.getByRole("button").click();
    await expect(th).toHaveAttribute("aria-sort", "ascending");
  }
  await page.locator(".clip-table tbody tr", { hasText: "Saltwater" }).filter({ hasText: "Wan 2.2" }).first().locator(".row-btn").click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Wan 2.2");
  // the bar: theme, plain words, the menu on a phone, the statement link and the dataset link
  if (phone) await page.getByRole("button", { name: "Menu" }).click();
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.getByRole("button", { name: /theme/i }).click();
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).not.toBe(bg);
  await expect(page.getByRole("link", { name: /Dataset/ })).toHaveAttribute("href", /doi\.org\/10\.5281\/zenodo\.16753748/);
  await page.getByRole("link", { name: /About this measure/ }).click();
  await expect(page.locator("#statement")).toBeInViewport();
  expect(await layoutProblems(page)).toEqual([]);
  expect(problems).toEqual([]);
});

// ----------------------------------------------------------------------------------------------- sync on a throttled CPU (390 px)

interface Pairs { pairs: number; max: number; over: number; hist: Record<string, number>; presented: Record<string, number> }

/** Play to the end with every VISIBLE video hooked on requestVideoFrameCallback. Callbacks run once per animation frame, and the ones of one
 *  frame share their first argument: so two videos' callbacks with the same timestamp saw the same screen, and the media times they report
 *  are the pictures on it. Their difference, in frames, is the sync. (`presentedFrames` counts what each video was handed.) */
async function playAndPair(page: Page): Promise<Pairs> {
  await page.evaluate(() => {
    const w = window as unknown as { __rec: Record<string, [number, number, number][]> };
    w.__rec = {};
    for (const v of document.querySelectorAll<HTMLVideoElement>("video")) {
      if (v.hidden) continue;
      const rec: [number, number, number][] = (w.__rec[v.dataset.paneVideo!] = []);
      const tick: VideoFrameRequestCallback = (now, m) => { rec.push([now, Math.round(m.mediaTime * 24), m.presentedFrames]); v.requestVideoFrameCallback(tick); };
      v.requestVideoFrameCallback(tick);
    }
  });
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible({ timeout: 30_000 });
  return page.evaluate(() => {
    const w = window as unknown as { __rec: Record<string, [number, number, number][]> };
    const real = w.__rec.real, other = Object.entries(w.__rec).find(([k]) => k !== "real")![1];
    const hist: Record<string, number> = {};
    let pairs = 0, max = 0, over = 0;
    for (const [t, f] of real) {
      const m = other.find((x) => Math.abs(x[0] - t) < 1);
      if (!m) continue;
      const d = Math.abs(f - m[1]);
      pairs++; hist[d] = (hist[d] ?? 0) + 1; max = Math.max(max, d); if (d > 1) over++;
    }
    const presented = Object.fromEntries(Object.entries(w.__rec).map(([k, r]) => [k, r.at(-1)![2] - r[0][2] + 1]));
    return { pairs, max, over, hist, presented };
  });
}

test("at 390 px with the CPU throttled 4x the three videos stay within one presented frame of each other: after scrubs, and during Play in both views", async ({ page }, info) => {
  phoneOnly(info);
  test.setTimeout(120_000);
  const problems = watchConsole(page);
  await open(page, DEFAULT, 0);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  try {
    expect(await page.evaluate(() => matchMedia("(max-width: 760px)").matches)).toBe(true);
    const slider = page.getByRole("slider", { name: "Frame" });
    const scrubTo = async (f: number) => slider.evaluate((el: HTMLInputElement, v) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(el, String(v));
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }, f);
    // after scrubs: the picture each pane PRESENTED next (a visible pane: requestVideoFrameCallback; the hidden one: its `seeked`)
    const landed: Record<number, Record<string, number>> = {};
    for (const f of [60, 120, 0, 37, 88, 5, 100, 119]) {
      const got = await page.evaluate(async (target) => {
        const vids = [...document.querySelectorAll<HTMLVideoElement>("video")];
        const p = vids.map((v) => v.hidden
          ? new Promise<[string, number]>((res) => { const done = () => setTimeout(() => res([v.dataset.paneVideo!, Math.floor(v.currentTime * 24 + 1e-6)]), 0); if (v.seeking) v.addEventListener("seeked", done, { once: true }); else setTimeout(done, 400); })
          : new Promise<[string, number]>((res) => v.requestVideoFrameCallback((_n, m) => res([v.dataset.paneVideo!, Math.round(m.mediaTime * 24)]))));
        const el = document.querySelector<HTMLInputElement>("input.range")!;
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(el, String(target));
        el.dispatchEvent(new Event("input", { bubbles: true }));
        return Object.fromEntries(await Promise.all(p.map((x) => Promise.race([x, new Promise<[string, number]>((r) => setTimeout(() => r(["timeout", -1]), 8000))]))));
      }, f);
      landed[f] = got as Record<string, number>;
      expect(got, `scrub to ${f}: all three panes on that frame`).toEqual({ real: f, heat: f, gen: f });
    }
    info.annotations.push({ type: "sync-scrubs", description: JSON.stringify(landed) });
    // during Play, Heat view (real + heat visible), then Bare (real + gen)
    for (const view of ["Heat", "Bare"]) {
      await page.getByRole("radio", { name: view }).check({ force: true });
      await slider.focus(); await page.keyboard.press("Home");
      await page.waitForFunction(() => [...document.querySelectorAll("video")].every((v) => !v.seeking));
      const r = await playAndPair(page);
      info.annotations.push({ type: `sync-play-${view}`, description: JSON.stringify(r) });
      // a busy main thread coalesces callbacks (39-68 screens were paired of ~121 in the runs): the count only has to mean something
      expect(r.pairs, `${view}: enough paired screens to mean something`).toBeGreaterThanOrEqual(20);
      expect(r.max, `${view}: the most frames two videos were apart on one screen`).toBeLessThanOrEqual(1);
      for (const [k, n] of Object.entries(r.presented)) expect(n / 121, `${view}: share of frames the ${k} video was handed`).toBeGreaterThanOrEqual(0.9);
      expect(await sliderValue(page)).toBe(120);
    }
    // the pause after a scrub in the middle of Play lands every pane on the frame the reader chose
    await slider.focus(); await page.keyboard.press("Home");
    await page.getByRole("button", { name: "Play" }).click();
    await page.waitForFunction(() => Number(document.querySelector<HTMLInputElement>("input.range")!.value) > 20);
    await scrubTo(80);
    await waitForFrame(page, 80);
  } finally {
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
  }
  expect(problems).toEqual([]);
});

// ------------------------------------------------------------------------------------------------------------------------- axe

async function axeSerious(page: Page) {
  const res = await new AxeBuilder({ page }).analyze();
  const hard = res.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  return { hard: hard.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`), all: res.violations.map((v) => `${v.id}:${v.impact}:${v.nodes.length}`) };
}

for (const [label, url] of [["default state", `/?clip=${DEFAULT}&plain=0`], ["plain words on", `/?clip=${DEFAULT}&plain=1`], ["a clip past its cap (hatched, the real pane's notice)", "/?clip=saltwater-pellets__gen45__N__5s&f=60&plain=0"]] as const) {
  test(`axe: ${label}: no serious or critical issue`, async ({ page }, info) => {
    const problems = watchConsole(page);
    await page.goto(url);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await waitForVideos(page);
    await page.locator(".relief").scrollIntoViewIfNeeded();
    await expect(page.locator(".relief-canvas, .relief-still, .relief [role=alert]").first()).toBeVisible({ timeout: 15_000 });
    await page.evaluate(() => scrollTo(0, 0));
    const { hard, all } = await axeSerious(page);
    info.annotations.push({ type: "axe-all-violations", description: all.join(", ") || "none" });
    expect(hard).toEqual([]);
    expect(all, "no violation of any impact (axe 4.14.0, all default rules)").toEqual([]);
    expect(problems).toEqual([]);
  });
}

// ---------------------------------------------------------------------------------------------------------------- text at 200 %

for (const plain of [0, 1]) {
  test(`text at 200 % at this width (plain words ${plain ? "on" : "off"}): nothing overflows, clips or leaves the page`, async ({ page }, info) => {
    desktopOnly(info);
    const problems = watchConsole(page);
    await open(page, DEFAULT, undefined);
    await page.goto(`/?clip=${DEFAULT}&plain=${plain}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(await layoutProblems(page), "at 100 %").toEqual([]);
    // text-only zoom, as plain.spec does: every type token doubled, the layout's widths left alone
    await page.addStyleTag({ content: ":root { --fs-title: 48px; --fs-section: 32px; --fs-body: 28px; --fs-small: 24px; }" });
    await page.waitForTimeout(150);
    expect(await layoutProblems(page), "text at 200 %").toEqual([]);
    // text must still be inside its panel: no element's text box wider than the card that holds it
    const spill = await page.evaluate(() => [...document.querySelectorAll<HTMLElement>(".panel, .stage, .key-strip, .picker, .title-row")].flatMap((p) => {
      const pr = p.getBoundingClientRect();
      return [...p.querySelectorAll<HTMLElement>("*")].filter((e) => !(e instanceof SVGElement) && !e.closest("svg, .table-frame, video, .visually-hidden") && e.getBoundingClientRect().width > 0
        && (e.getBoundingClientRect().right > pr.right + 1 || e.getBoundingClientRect().left < pr.left - 1)).map((e) => `${e.tagName.toLowerCase()}.${e.className.toString().split(" ")[0]} out of ${p.className.toString().split(" ")[0]}`);
    }));
    expect(spill).toEqual([]);
    await page.screenshot({ path: `${process.env.VERIFY_SHOTS ?? "test-results"}/zoom200-text-plain${plain}-${info.project.name}.png`, fullPage: false });
    expect(problems).toEqual([]);
  });
}

test("the page zoomed to 200 % (a 720 px viewport at 1440): no sideways scroll, the stage and the evidence row hold", async ({ page }, info) => {
  desktopOnly(info);
  const problems = watchConsole(page);
  await page.setViewportSize({ width: 720, height: 450 });
  await open(page);
  expect(await layoutProblems(page)).toEqual([]);
  await page.locator(".evidence").scrollIntoViewIfNeeded();
  expect(await layoutProblems(page)).toEqual([]);
  await page.setViewportSize({ width: 360, height: 450 });          // 400 %
  await page.waitForTimeout(150);
  expect(await layoutProblems(page), "at 400 %").toEqual([]);
  expect(problems).toEqual([]);
});

// ---------------------------------------------------------------------------------------------------------------- reduced motion

test("reduced motion is honoured: nothing autoplays, no transition runs, the relief is a still until asked, a table pick scrolls at once", async ({ page }, info) => {
  const problems = watchConsole(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page);
  // nothing plays by itself, nothing animates
  expect(await page.evaluate(() => [...document.querySelectorAll("video")].every((v) => v.paused))).toBe(true);
  expect(await page.evaluate(() => document.getAnimations().length)).toBe(0);
  const durations = await page.evaluate(() => [...document.querySelectorAll(".btn, .seg-opt, .bar-nav a, .theme-btn")].map((e) => getComputedStyle(e).transitionDuration));
  expect(durations.length).toBeGreaterThan(3);
  expect(durations.filter((d) => d.split(",").some((x) => parseFloat(x) !== 0))).toEqual([]);
  // the relief is a still, with a button to orbit it; asking arms the canvas
  await page.locator(".relief").scrollIntoViewIfNeeded();
  await expect(page.locator(".relief-still")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".relief-canvas")).toHaveCount(0);
  await page.getByRole("button", { name: "Orbit the surfaces" }).click();
  await expect(page.locator(".relief-canvas")).toBeVisible({ timeout: 15_000 });
  // a pick from the table scrolls the stage into view at once (it falls back from smooth to instant)
  await page.locator(".clip-table").scrollIntoViewIfNeeded();
  const far = await page.evaluate(() => scrollY);
  expect(far).toBeGreaterThan(1000);
  await page.locator(".clip-table tbody tr", { hasText: "Air" }).first().locator(".row-btn").click();
  await page.waitForFunction(() => scrollY < 150, undefined, { timeout: 300 });
  // Play still plays (reduced motion removes decoration, not the content the reader asked for)
  await page.evaluate(() => scrollTo(0, 0));
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  await page.getByRole("button", { name: "Pause" }).click();
  expect(problems).toEqual([]);
  info.annotations.push({ type: "reduced-motion", description: `far scroll ${far}px, transitions ${durations.length} checked` });
});

// ------------------------------------------------------------------------------------------------ the items DESIGN.md left for 4.6

test("the picker holds still when the finding wraps (the title row used to reflow by 24 px and carry it down), and every finding fits its column", async ({ page }, info) => {
  desktopOnly(info);
  const tops: Record<string, { picker: number; lines: number }> = {};
  for (const id of [DEFAULT, "saltwater-pellets__gen45__N__5s", "air__wan22__N__5s", "freshwater__wan22__B__5s", "saltwater-pellets__gen45__D__10s"]) {
    await page.goto(`/?clip=${id}&plain=0`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    tops[id] = await page.evaluate(() => {
      const f = document.querySelector(".finding") as HTMLElement;
      return { picker: Math.round(document.querySelector(".picker")!.getBoundingClientRect().top), lines: Math.round(f.getBoundingClientRect().height / parseFloat(getComputedStyle(f).lineHeight)) };
    });
  }
  info.annotations.push({ type: "title-row", description: JSON.stringify(tops) });
  expect(new Set(Object.values(tops).map((t) => t.lines)).size, "the test covers findings of different lengths").toBeGreaterThan(1);
  expect(new Set(Object.values(tops).map((t) => t.picker)).size, "the picker's top is the same whatever the finding").toBe(1);
});

test("at 768 the evidence row is two plus one: the plan view and the relief side by side, the numbers across the width, in reading order", async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1000 });
  await open(page);
  const boxes = await page.evaluate(() => [".panel-plan", ".panel-relief", ".panel-numbers"].map((s) => { const r = document.querySelector(s)!.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), b: Math.round(r.bottom) }; }));
  const [plan, relief, numbers] = boxes;
  expect(plan.y).toBe(relief.y);
  expect(plan.w).toBeGreaterThan(300);
  expect(relief.x).toBeGreaterThan(plan.x);
  expect(numbers.y).toBeGreaterThanOrEqual(Math.max(plan.b, relief.b));
  expect(numbers.w).toBeGreaterThan(plan.w + relief.w);
  expect(await layoutProblems(page)).toEqual([]);
  await page.setViewportSize({ width: 1024, height: 900 });         // 1024 is the first width of three columns
  await page.waitForTimeout(100);
  const three = await page.evaluate(() => [".panel-plan", ".panel-relief", ".panel-numbers"].map((s) => Math.round(document.querySelector(s)!.getBoundingClientRect().y)));
  expect(new Set(three).size).toBe(1);
});

test("B, D and N are named above the fold: the legend says the chosen one in a word, and every option's tooltip says all three with the engine's wording", async ({ page }, info) => {
  const phone = info.project.name.startsWith("phone");
  await open(page, DEFAULT);
  const legend = phone ? page.locator(".pick-select .field-label", { hasText: "Prompt" }) : page.locator(".picker legend", { hasText: "Prompt" });
  await expect(legend).toHaveText("Prompt · documentary");
  if (!phone) {
    const opts = page.getByRole("group", { name: "Choose a clip" }).locator("fieldset", { hasText: "Prompt" }).locator("label.seg-opt");
    await expect(opts).toHaveCount(3);
    await expect(opts.nth(0)).toHaveAttribute("title", /^B: continue\. The engine was told: .The scene continues\..$/);
    await expect(opts.nth(1)).toHaveAttribute("title", /^D: dive\. The engine was told: .Underwater, the camera glides slowly forward/);
    await expect(opts.nth(2)).toHaveAttribute("title", /^N: documentary\. The engine was told: .The scene continues, as if in a documentary about a tank\..$/);
  }
  await page.goto(`/?clip=air__gen45__D__5s`);
  await expect(legend).toHaveText("Prompt · dive");
  expect(await layoutProblems(page)).toEqual([]);
});

test("one key line relates the heat's scale to D: D 1 is the floor's gap, D 3 is three times it, and where that is past the ramp's clip it says so", async ({ page }) => {
  await open(page, DEFAULT);
  const scale = page.locator(".ramp-scale");
  await expect(scale).toContainText("D 1 is a mean gap of 0.125, D 3 is 0.374.");
  await expect(scale).not.toContainText("past the clip");
  await page.goto("/?clip=air__gen45__D__5s");
  await expect(scale).toContainText("D 1 is a mean gap of 0.208, D 3 is 0.623, past the clip.");
  expect(await layoutProblems(page)).toEqual([]);
});

test("the D curve spends at least 20 px of its 48 px track between the D = 1 and D = 3 lines on the default clip (it was 15)", async ({ page }) => {
  await open(page, DEFAULT);
  const ys = await page.locator(".d-track .ref").evaluateAll((els) => els.map((e) => Number(e.getAttribute("y1"))));
  expect(ys).toHaveLength(2);
  expect(Math.abs(ys[0] - ys[1])).toBeGreaterThanOrEqual(20);
  const track = await page.locator(".tracks").evaluate((s) => Number(s.getAttribute("height")));
  expect(Math.max(...ys)).toBeLessThan(track);
});
