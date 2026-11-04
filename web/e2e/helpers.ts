import { expect, test, type Page } from "@playwright/test";
import { decode } from "fast-png";

export const DEFAULT = "freshwater-basicEnhance__gen45__N__5s";
export const CALM = "air__gen45__D__5s";          // D never passes 3 (the fixture's clip, and a real one)

/** Third-party noise that is not ours and not fixable here. Everything else in the console fails the test. */
export const KNOWN_NOISE: { match: RegExp; why: string }[] = [
  { match: /THREE\.Clock: This module has been deprecated/, why: "@react-three/fiber 9.8.2 (the latest stable) builds a THREE.Clock and three 0.186.1 warns about it. Task 4.6 checked: r3f 10.0.0-alpha.6 (18 days old) silences it but needs the /legacy import and is a pre-release major, so it is not adopted for a console-only notice; three 0.187.0 is under two weeks old. Drop this entry when r3f 10 is stable." },
  { match: /GL Driver Message|GPU stall due to ReadPixels/, why: "headless Chromium's software GL reports a driver note while the relief draws" },
  { match: /Download the React DevTools/, why: "react-dom's dev-build hint (an info message)" },
  { match: /\[vite\] (connecting|connected)/, why: "vite's dev-server handshake (a debug message)" },
];

export function watchConsole(page: Page): string[] {
  const problems: string[] = [];
  const keep = (text: string) => !KNOWN_NOISE.some((k) => k.match.test(text));
  page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && keep(m.text())) problems.push(`${m.type()}: ${m.text()}`); });
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  return problems;
}

/** Skip, saying why, when the real assets are not being served. A dev server that answers a missing file with its home page is
 *  200 text/html, so "ok" is not enough: the answer must be JSON (vite/media-dev.ts answers 404, but the check does not rely on it). */
export async function needAssets(page: Page) {
  const r = await page.request.get("/media/clips.json");
  const json = (r.headers()["content-type"] ?? "").includes("json");
  test.skip(!r.ok() || !json, "runs/assets is not there (or not serving JSON): the e2e reads the real files (see playwright.config.ts)");
}

export async function open(page: Page, clip = DEFAULT, f?: number) {
  await page.goto(`/?clip=${clip}${f === undefined ? "" : `&f=${f}`}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await waitForVideos(page);
}

export async function waitForVideos(page: Page) {
  await page.waitForFunction(() => {
    const v = [...document.querySelectorAll("video")];
    return v.length === 3 && v.every((x) => x.readyState >= 2 && !x.seeking);
  }, undefined, { timeout: 20_000 });
}

export const frames = (page: Page) => page.evaluate(() => [...document.querySelectorAll("video")].map((v) => Math.floor(v.currentTime * 24 + 1e-6)));

/** Wait until every video has finished seeking to the middle of frame f (the deterministic capture: `?f=n`, then this, then shoot). */
export async function waitForFrame(page: Page, f: number, fps = 24) {
  await page.waitForFunction(([frame, rate]) => {
    const v = [...document.querySelectorAll("video")];
    return v.length === 3 && v.every((x) => x.readyState >= 2 && !x.seeking && Math.abs(x.currentTime - (frame + 0.5) / rate) < 1e-3);
  }, [f, fps] as const, { timeout: 20_000 });
}

/**
 * Presented frames, not currentTime: arm requestVideoFrameCallback on the visible videos, run `action`, and read the media time of the
 * picture each one presented next. A hidden video presents nothing; its frame is read after its `seeked`. Returns frame numbers
 * keyed by pane.
 */
export async function presentedAfter(page: Page, action: () => Promise<void>): Promise<Record<string, number>> {
  await page.evaluate(() => {
    const w = window as unknown as { __presented: Record<string, Promise<number>> };
    w.__presented = {};
    for (const v of document.querySelectorAll<HTMLVideoElement>("video")) {
      const pane = v.dataset.paneVideo!;
      if (v.hidden) {
        w.__presented[pane] = new Promise((res) => {
          const done = () => res(Math.floor(v.currentTime * 24 + 1e-6));
          if (!v.seeking) setTimeout(done, 400); else v.addEventListener("seeked", () => setTimeout(done, 0), { once: true });
        });
      } else {
        w.__presented[pane] = new Promise((res) => v.requestVideoFrameCallback((_now, m) => res(Math.round(m.mediaTime * 24))));
      }
    }
  });
  await action();
  return page.evaluate(async () => {
    const w = window as unknown as { __presented: Record<string, Promise<number>> };
    const out: Record<string, number> = {};
    for (const [k, p] of Object.entries(w.__presented)) out[k] = await Promise.race([p, new Promise<number>((r) => setTimeout(() => r(-1), 5000))]);
    return out;
  });
}

export async function sliderValue(page: Page) {
  return Number(await page.getByRole("slider", { name: "Frame" }).inputValue());
}

/** Gold pixels outside the media: screenshot with every picture masked out, then count pixels of the page's own --gold. */
export async function goldPixels(page: Page): Promise<number> {
  const gold = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--gold").trim());
  const want = [1, 3, 5].map((i) => parseInt(gold.slice(i, i + 2), 16));
  const mask = page.locator("video, .relief-canvas, .relief-still, .start-fig img, .pane-frame, .floor-thumb img");
  const png = decode(await page.screenshot({ fullPage: true, mask: [mask], maskColor: "#000000" }));
  const ch = png.channels;
  let n = 0;
  for (let i = 0; i < png.data.length; i += ch)
    if (Math.abs(png.data[i] - want[0]) <= 2 && Math.abs(png.data[i + 1] - want[1]) <= 2 && Math.abs(png.data[i + 2] - want[2]) <= 2) n++;
  return n;
}

export interface PlayCount { presented: number; calls: number; paused: boolean }

/**
 * Press Play and let the clip run to its end (Play stops by itself on the last frame), counting for EVERY video, visible or hidden, how
 * many pictures the compositor was handed (`presentedFrames`), how many callbacks the page saw, and whether it ended paused. Starts
 * from the frame the page is on; use `open(page, id, 0)` for a full run.
 */
export async function playAndCount(page: Page): Promise<Record<string, PlayCount>> {
  await page.evaluate(() => {
    const w = window as unknown as { __count: Record<string, { first: number | null; last: number; calls: number }> };
    w.__count = {};
    for (const v of document.querySelectorAll<HTMLVideoElement>("video")) {
      const c = { first: null as number | null, last: 0, calls: 0 };
      w.__count[v.dataset.paneVideo!] = c;
      const tick: VideoFrameRequestCallback = (_now, m) => { c.first ??= m.presentedFrames; c.last = m.presentedFrames; c.calls++; v.requestVideoFrameCallback(tick); };
      v.requestVideoFrameCallback(tick);
    }
  });
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible({ timeout: 15_000 });
  return page.evaluate(() => {
    const w = window as unknown as { __count: Record<string, { first: number | null; last: number; calls: number }> };
    const out: Record<string, { presented: number; calls: number; paused: boolean }> = {};
    for (const v of document.querySelectorAll<HTMLVideoElement>("video")) {
      const c = w.__count[v.dataset.paneVideo!];
      out[v.dataset.paneVideo!] = { presented: c.first === null ? 0 : c.last - c.first + 1, calls: c.calls, paused: v.paused };
    }
    return out;
  });
}

/** What the layout gets wrong when the data is long: anything drawn past the viewport, or cut off inside its own box. */
export async function layoutProblems(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    const W = document.documentElement.clientWidth;
    if (document.documentElement.scrollWidth > W) out.push(`the page scrolls sideways (${document.documentElement.scrollWidth} > ${W})`);
    const name = (e: Element) => `${e.tagName.toLowerCase()}.${(e as HTMLElement).className?.toString().split(" ")[0] ?? ""} "${(e.textContent ?? "").trim().slice(0, 30)}"`;
    for (const e of document.body.querySelectorAll("*")) {
      const cs = getComputedStyle(e as HTMLElement);
      if (cs.display === "none" || cs.visibility === "hidden" || e.closest(".visually-hidden, .skip, [hidden]")) continue;
      const r = e.getBoundingClientRect();
      if (r.width <= 2 || r.height <= 2) continue;          // a 1 px visually-hidden box is not on the page
      if (e.closest(".table-frame") === null && (r.right > W + 0.5 || r.left < -0.5) && !(e instanceof SVGElement)) out.push(`${name(e)} spans ${Math.round(r.left)}..${Math.round(r.right)} of ${W}`);
      if (["hidden", "clip"].includes(cs.overflowX) && (e as HTMLElement).scrollWidth > (e as HTMLElement).clientWidth + 1 && !(e instanceof SVGElement) && !e.matches(".pane-frame, .relief-frame, .seg-opt input"))
        out.push(`${name(e)} clips its own text sideways (${(e as HTMLElement).scrollWidth} > ${(e as HTMLElement).clientWidth})`);
    }
    return out;
  });
}

/** The page's text with times ("f0 · 0.00 s", a time is a time) taken out: a D or a V of 0.00 would be a lie about what was not measured. */
export const readable = (page: Page) => page.evaluate(() => document.body.innerText.replace(/f\d+ · \d+\.\d{2} s/g, ""));
