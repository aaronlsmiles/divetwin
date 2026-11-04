import { expect, test } from "@playwright/test";
import { CALM, DEFAULT, goldPixels, needAssets, open, playAndCount, presentedAfter, sliderValue, waitForFrame, waitForVideos, watchConsole, type PlayCount } from "./helpers";

test.beforeEach(async ({ page }) => { await needAssets(page); });

test("opens on the finding with a clean console, no horizontal scroll, and the cursor on the departure", async ({ page }) => {
  const problems = watchConsole(page);
  await open(page);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Freshwater, enhanced · Gen-4.5 · prompt N · 5 s");
  await expect(page.locator(".finding")).toHaveText("D passes 3 at frame 88 (3.7 s), 711 su in; every pixel still verified (V 1.00)");
  expect(await sliderValue(page)).toBe(88);
  await expect(page.locator(".readout")).toHaveText("f88 · 3.67 s");
  await expect(page.locator(".evidence .panel")).toHaveCount(3);
  const thumb = page.locator("[data-floor-map] img");
  await expect(thumb).toBeVisible();
  await expect.poll(() => thumb.evaluate((i: HTMLImageElement) => i.naturalWidth)).toBeGreaterThan(0);
  await expect(page.locator("[data-floor-map]")).toContainText("where mono depth already errs on the real tank; display only, the same for every frame");
  await page.locator(".relief").scrollIntoViewIfNeeded();
  await expect(page.locator(".relief-canvas, .relief-still").first()).toBeVisible({ timeout: 15_000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(problems).toEqual([]);
});

test("every control works by keyboard: scrubber, play, dream switch, picker, theme, table", async ({ page }, info) => {
  const problems = watchConsole(page);
  await open(page);
  const slider = page.getByRole("slider", { name: "Frame" });
  await slider.focus();
  await page.keyboard.press("ArrowRight"); expect(await sliderValue(page)).toBe(89);
  await page.keyboard.press("ArrowLeft"); await page.keyboard.press("ArrowLeft"); expect(await sliderValue(page)).toBe(87);
  await page.keyboard.press("Shift+ArrowRight"); expect(await sliderValue(page)).toBe(99);
  await page.keyboard.press("Shift+ArrowLeft"); expect(await sliderValue(page)).toBe(87);
  await page.keyboard.press("Home"); expect(await sliderValue(page)).toBe(0);
  await page.keyboard.press("End"); expect(await sliderValue(page)).toBe(120);
  // play: a toggle button, reached by Tab order from the slider's neighbours, operated with Space
  const play = page.getByRole("button", { name: "Play" });
  await play.focus(); await page.keyboard.press("Space");
  await expect(page.getByRole("button", { name: "Pause" })).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Space");
  await expect(page.getByRole("button", { name: "Play" })).toHaveAttribute("aria-pressed", "false");
  // the dream switch: native radios, arrow keys
  await page.getByRole("radio", { name: "Heat" }).focus(); await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("radio", { name: "Bare" })).toBeChecked();
  await expect(page.locator('video[data-pane-video="gen"]')).toBeVisible();
  // the picker: arrow keys on the engine radios (selects on a phone)
  if (info.project.name.startsWith("desktop")) {
    await page.getByRole("radio", { name: "Wan 2.2" }).focus(); await page.keyboard.press("Space");
  } else {
    await page.getByLabel("Engine").selectOption("wan22");
  }
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Wan 2.2");
  expect(new URL(page.url()).searchParams.get("clip")).toBe("freshwater-basicEnhance__wan22__N__5s");
  // the table: sort by a header with Enter, load a row with Enter
  const th = page.getByRole("columnheader", { name: /^Travel/ });
  await th.getByRole("button").focus(); await page.keyboard.press("Enter");
  await expect(th).toHaveAttribute("aria-sort", "ascending");
  await page.locator(".clip-table tbody tr .row-btn").first().focus(); await page.keyboard.press("Enter");
  await expect(page.locator(".clip-table tbody tr.is-active")).toHaveCount(1);
  // the theme toggle
  const before = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  if (info.project.name.startsWith("phone")) await page.getByRole("button", { name: "Menu" }).click();
  await page.getByRole("button", { name: /theme/i }).focus(); await page.keyboard.press("Enter");
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).not.toBe(before);
  expect(problems).toEqual([]);
});

test("after a scrub the panes have PRESENTED the same frame (requestVideoFrameCallback), the hidden view too once it is shown", async ({ page }) => {
  await open(page);
  const slider = page.getByRole("slider", { name: "Frame" });
  await slider.focus();
  for (const key of ["Home", "Shift+ArrowRight", "Shift+ArrowRight", "End", "Shift+ArrowLeft"]) {
    const shown = await presentedAfter(page, () => page.keyboard.press(key));
    const f = await sliderValue(page);
    expect(shown.real, `${key}: the real pane presented the cursor's frame`).toBe(f);
    expect(shown.heat, `${key}: the heat pane presented the cursor's frame`).toBe(f);
    expect(Math.abs(shown.real - shown.heat), `${key}: ${JSON.stringify(shown)}`).toBeLessThanOrEqual(1);
  }
  // the hidden view: switch to Bare and scrub again; now it is the visible one and presents
  await page.getByRole("radio", { name: "Bare" }).check({ force: true });
  await slider.focus();
  const shown = await presentedAfter(page, () => page.keyboard.press("Home"));
  expect(shown.real).toBe(0);
  expect(shown.gen).toBe(0);
  expect(Math.abs(shown.real - shown.gen)).toBeLessThanOrEqual(1);
  // and after play, a pause lands all three on the cursor's frame (the seeked check: nothing is still seeking)
  await page.getByRole("button", { name: "Play" }).click();
  await page.waitForTimeout(600);
  await page.getByRole("button", { name: "Pause" }).click();
  const f = await sliderValue(page);
  await waitForFrame(page, f);
});

/** The visible panes were handed >= 90 % of the 121 pictures; the hidden view played nothing (paused, at most 2 pictures: a seek's own). */
function expectPlayed(counts: Record<string, PlayCount>, visible: string[], hidden: string, total = 121) {
  for (const pane of visible) {
    test.info().annotations.push({ type: "presented", description: `${pane}: ${counts[pane].presented} of ${total} presented, ${counts[pane].calls} callbacks ran` });
    expect(counts[pane].presented, `${pane} presented ${counts[pane].presented} of ${total}`).toBeGreaterThanOrEqual(Math.ceil(0.9 * total));
  }
  expect(counts[hidden].paused, `${hidden} (hidden) stays paused`).toBe(true);
  expect(counts[hidden].presented, `${hidden} (hidden) presented ${counts[hidden].presented}`).toBeLessThanOrEqual(2);
}

test("Play plays (Heat view): the real pane and the heat view present at least 90 % of the frames over a 5 s clip, the bare view plays nothing, and the cursor ends on the last frame", async ({ page }) => {
  await open(page, DEFAULT, 0);
  expectPlayed(await playAndCount(page), ["real", "heat"], "gen");
  expect(await sliderValue(page)).toBe(120);
  await waitForVideos(page);
});

test("Play plays (Bare view): the real pane and the bare clip present at least 90 %, the heat view plays nothing", async ({ page }) => {
  await open(page, DEFAULT, 0);
  await page.getByRole("radio", { name: "Bare" }).check({ force: true });
  await waitForVideos(page);
  expectPlayed(await playAndCount(page), ["real", "gen"], "heat");
  expect(await sliderValue(page)).toBe(120);
});

test("a scrub during Play ends Play and lands where it was told: End shows Pause go, the slider on 120, and the panes present 120", async ({ page }) => {
  await open(page, DEFAULT, 0);
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  await page.waitForTimeout(500);
  const slider = page.getByRole("slider", { name: "Frame" });
  // keep the media time of the LAST picture each visible pane presents (a picture or two of the play that was running may still arrive
  // as the seek lands; what matters is the one the panes are left showing)
  await page.evaluate(() => {
    const w = window as unknown as { __last: Record<string, number> };
    w.__last = {};
    for (const v of document.querySelectorAll<HTMLVideoElement>("video:not([hidden])")) {
      const tick: VideoFrameRequestCallback = (_now, m) => { w.__last[v.dataset.paneVideo!] = Math.round(m.mediaTime * 24); v.requestVideoFrameCallback(tick); };
      v.requestVideoFrameCallback(tick);
    }
  });
  await slider.focus();
  await page.keyboard.press("End");
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible();                       // Pause is gone: Play ended
  await page.waitForTimeout(800);                                                                 // long enough for a stale picture to undo it (it fell to 26 within 300 ms)
  expect(await sliderValue(page)).toBe(120);
  const shown = await page.evaluate(() => (window as unknown as { __last: Record<string, number> }).__last);
  expect(shown.real, `real is showing ${shown.real}`).toBe(120);
  expect(shown.heat, `heat is showing ${shown.heat}`).toBe(120);
  await waitForFrame(page, 120);
  // and Home during a second Play
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  await page.waitForTimeout(400);
  await slider.focus();
  await page.keyboard.press("Home");
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible();
  await page.waitForTimeout(500);
  expect(await sliderValue(page)).toBe(0);
  await waitForFrame(page, 0);
});

test("deterministic capture for the film (task 5.1): ?f=n, wait for every video to have seeked, and all three are on that frame", async ({ page }) => {
  for (const f of [0, 37, 88, 120]) {
    await page.goto(`/?clip=${DEFAULT}&f=${f}`);
    await waitForFrame(page, f);
    expect(await sliderValue(page)).toBe(f);
    expect(await page.evaluate(() => [...document.querySelectorAll("video")].map((v) => v.seeking))).toEqual([false, false, false]);
  }
});

test("with the clip that never passes 3 there is no gold outside the media; with the default clip there is", async ({ page }) => {
  await open(page, CALM, 60);
  const slider = page.getByRole("slider", { name: "Frame" });
  for (const key of ["Home", "Shift+ArrowRight", "End"]) {
    await slider.focus(); await page.keyboard.press(key);
    expect(await goldPixels(page), `calm clip after ${key}`).toBe(0);
  }
  await expect(page.locator(".lead")).not.toHaveClass(/is-gold/);
  await open(page, DEFAULT, 100);
  await expect(page.locator(".lead")).toHaveClass(/is-gold/);
  expect(await goldPixels(page), "the control: the departing clip does show gold").toBeGreaterThan(50);
});

test("URL state: the frame and the clip survive a reload, and back returns to the first clip", async ({ page }) => {
  await open(page, DEFAULT, 40);
  await page.waitForTimeout(500);
  expect(new URL(page.url()).searchParams.get("f")).toBe("40");
  await page.reload(); await waitForVideos(page);
  expect(await sliderValue(page)).toBe(40);
  await page.goto(`/?clip=${CALM}&f=60`); await waitForVideos(page);
  await page.goBack();                                          // a full navigation back: wait for the URL, then for the page to load again
  await page.waitForURL((u) => u.searchParams.get("clip") === DEFAULT, { timeout: 20_000 });
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Freshwater, enhanced", { timeout: 20_000 });
});

test("layout: the evidence row is three columns on a desktop and one on a phone; the relief is live on a desktop and a still on a phone, never trapping scroll", async ({ page }, info) => {
  const problems = watchConsole(page);
  await open(page);
  if (info.project.name.startsWith("desktop")) {
    // the first screen at 1440 x 900: the evidence row's headers, and the first line under each, show above the fold (design pass)
    const heads = () => page.locator(".evidence .panel h2").evaluateAll((hs) => hs.map((h) => h.getBoundingClientRect().bottom + window.scrollY));
    // a first visit: the plain-words invite is under the finding, and the headers still show
    if (await page.locator(".pw-invite").count()) {
      for (const b of await heads()) expect(b, "an evidence header below the fold on a first visit").toBeLessThan(900);
      await page.getByRole("button", { name: "Not now" }).click();
    }
    // once it is answered, the headers and the first line under each
    const h = await heads();
    expect(h).toHaveLength(3);
    for (const b of h) expect(b, "an evidence header (and the line under it) below the fold").toBeLessThan(900 - 40);
  }
  await page.locator(".relief").scrollIntoViewIfNeeded();
  const boxes = await page.locator(".evidence .panel").evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width }; }));
  const stage = await page.locator(".panes .pane").evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y }; }));
  const key = await page.locator(".key-strip .ramps").boundingBox();
  const thumb = await page.locator("[data-floor-map]").boundingBox();
  expect(Math.round((await page.locator("[data-floor-map] img").boundingBox())!.width)).toBe(144);
  // the scrubber sits straight under the panes, and the key strip under the scrubber
  const bottom = (sel: string) => page.locator(sel).evaluate((e) => e.getBoundingClientRect().bottom);
  const top = (sel: string) => page.locator(sel).evaluate((e) => e.getBoundingClientRect().top);
  expect(await top(".scrubber")).toBeGreaterThanOrEqual(await bottom(".panes"));
  expect(await top(".scrubber") - await bottom(".panes")).toBeLessThan(16);
  expect(await top(".key-strip")).toBeGreaterThanOrEqual(await bottom(".scrubber"));
  if (info.project.name.startsWith("desktop")) {
    expect(thumb!.x, "the map sits beside the ramps at 1440").toBeGreaterThanOrEqual(key!.x + key!.width - 1);
    expect(Math.abs(thumb!.y - key!.y)).toBeLessThan(8);
  } else {
    expect(thumb!.y, "the map sits under the ramps at 390").toBeGreaterThanOrEqual(key!.y + key!.height - 1);
  }
  if (info.project.name.startsWith("desktop")) {
    expect(new Set(boxes.map((b) => Math.round(b.y))).size).toBe(1);
    expect(stage[0].y).toBeCloseTo(stage[1].y, 0);
    await expect(page.locator(".relief-canvas")).toBeVisible({ timeout: 15_000 });
    expect(await page.locator(".relief-canvas").evaluate((c) => getComputedStyle(c).touchAction)).toBe("pan-y");
  } else {
    expect(new Set(boxes.map((b) => Math.round(b.x))).size).toBe(1);
    // phone order: the numbers first (D at full width), then the plan view, then the relief
    const y = (sel: string) => page.locator(sel).evaluate((e) => e.getBoundingClientRect().y);
    const [numbersY, planY, reliefY] = [await y(".panel-numbers"), await y(".panel-plan"), await y(".panel-relief")];
    expect(numbersY, "the numbers come first").toBeLessThan(planY);
    expect(planY, "then the plan view").toBeLessThan(reliefY);
    const lead = await page.locator(".numbers .n-lead").boundingBox(), dl = await page.locator(".numbers").boundingBox();
    expect(Math.abs(lead!.width - dl!.width), "D leads at full width").toBeLessThan(3);
    // the longest note (path agreement) takes the whole width; with plain words off the departure does too, so nothing sits beside a gap
    for (const sel of [".numbers .n-agree", ".numbers .n-dep"]) {
      const b = await page.locator(sel).boundingBox();
      expect(Math.abs(b!.width - dl!.width), `${sel} at full width`).toBeLessThan(3);
    }
    expect(stage[1].y).toBeGreaterThan(stage[0].y);                 // the panes stack
    await expect(page.locator(".relief-still")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".relief-canvas")).toHaveCount(0);
    await page.getByRole("button", { name: "Orbit the surfaces" }).click();
    await expect(page.locator(".relief-canvas")).toBeVisible({ timeout: 15_000 });
    expect(await page.locator(".relief-canvas").evaluate((c) => getComputedStyle(c).touchAction)).toBe("pan-y");
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(problems).toEqual([]);
});

test("the table lists all 35 clips; past the cap it says unverifiable and never 0.00; a row loads the stage", async ({ page }) => {
  await open(page);
  await expect(page.locator(".clip-table tbody tr")).toHaveCount(35);
  const pellets = page.locator(".clip-table tbody tr", { hasText: "Saltwater, pellets" }).first();
  await expect(pellets).toContainText("unverifiable");
  expect(await page.locator(".clip-table tbody").innerText()).not.toContain("0.00");
  await page.locator(".clip-table tbody tr", { hasText: "Air" }).filter({ hasText: "Wan 2.2" }).first().locator(".row-btn").click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Air · Wan 2.2");
});

test("on a phone the table is two-line rows (the breadcrumb with its length, then D; then V, the departure and the travel) and nothing clips", async ({ page }, info) => {
  test.skip(!info.project.name.startsWith("phone"), "the phone layout");
  await open(page);
  await page.locator(".clip-table").scrollIntoViewIfNeeded();
  const frame = page.locator(".table-frame");
  expect(await frame.evaluate((e) => e.scrollWidth <= e.clientWidth), "the table does not scroll sideways").toBe(true);
  const clipped = await page.locator(".clip-table tbody tr").evaluateAll((trs) => trs.flatMap((tr) => {
    const row = tr.getBoundingClientRect();
    return [...tr.querySelectorAll("td")].filter((td) => getComputedStyle(td).display !== "none").flatMap((td) => {
      const r = td.getBoundingClientRect();
      const inside = r.left >= row.left - 0.5 && r.right <= row.right + 0.5 && r.top >= row.top - 0.5 && r.bottom <= row.bottom + 0.5;
      return td.scrollWidth > td.clientWidth + 0.5 || !inside ? [`${tr.querySelector(".row-btn")?.getAttribute("aria-label")} ${td.dataset.col}`] : [];
    });
  }));
  expect(clipped, "cells that overflow their frame").toEqual([]);
  // a 5 s row: line 1 is the breadcrumb (with the length) and D; line 2 is V, the departure and the travel; no 10 s cells
  const row = page.locator(".clip-table tbody tr").first();
  const top = (col: string) => row.locator(`[data-col="${col}"]`).evaluate((e) => Math.round(e.getBoundingClientRect().top));
  expect(await top("d5")).toBe(await top("recording"));
  const line2 = [await top("v5"), await top("departure"), await top("travel")];
  expect(new Set(line2).size).toBe(1);
  expect(line2[0]).toBeGreaterThan(await top("d5"));
  const name = (await row.locator(".row-btn").getAttribute("aria-label"))!;            // "<recording> · <engine> · prompt <p> · 5 s"
  const crumb = name.slice((await row.locator(".row-btn").innerText()).length);
  expect(crumb).toMatch(/ · prompt [DBN] · 5 s$/);
  // the crumb is drawn with a no-break space before every "·" (and inside "prompt N" and "5 s"), so a wrapped row never starts a line with "·"
  const drawn = await row.locator('[data-col="recording"]').evaluate((e) => getComputedStyle(e, "::after").content);
  expect(drawn.replace(/[\u00a0\u2060]/g, (c) => (c === "\u00a0" ? " " : ""))).toContain(crumb);
  expect(drawn).not.toMatch(/ ·/);
  expect(drawn).toContain("\u00a0·");
  await expect(row.locator('[data-col="d10"]')).toBeHidden();
  // a 10 s dive shows D and V at 10 s
  const long = page.locator(".clip-table tbody tr").filter({ has: page.locator('.row-btn[aria-label$="10 s"]') }).first();
  await expect(long.locator('[data-col="d10"]')).toBeVisible();
  await expect(long.locator('[data-col="v10"]')).toBeVisible();
});

test("below the fold: the statement, the wall test's limit, the notes and the credits", async ({ page }) => {
  await open(page, "air__wan22__N__5s");
  await expect(page.locator("#statement")).toContainText("uncorrected stereo units (su)");
  await expect(page.locator("#statement")).toContainText("cannot follow a dream out through the far end as measured");   // Air has no far wall (call 28)
  await expect(page.locator(".plan figcaption")).toContainText("out through the far end as measured");
  await expect(page.getByText(/far wall/)).toHaveCount(0);
  await expect(page.locator('[data-note="air-wan-n-mask"]')).toBeVisible();
  await expect(page.getByText("10.5281/zenodo.16753748").first()).toBeVisible();
  await expect(page.getByText(/ZED Mini/)).toBeVisible();
});

test("past a cap the real pane says why, and 'Back to the last checked frame' lands there on every pane", async ({ page }) => {
  const problems = watchConsole(page);
  await open(page, "saltwater-pellets__gen45__N__5s", 60);
  const notice = page.locator('[data-pane="real"] .pane-notice');
  await expect(notice).toContainText("From frame 20, nothing here can be checked");
  await notice.getByRole("button", { name: "Back to the last checked frame" }).click();
  await expect(notice).toHaveCount(0);
  expect(await sliderValue(page)).toBe(19);
  await page.waitForFunction(() => [...document.querySelectorAll("video")].every((v) => !v.seeking && Math.abs(v.currentTime - 19.5 / 24) < 1e-3));
  expect(problems).toEqual([]);
});
