#!/usr/bin/env python3
"""Capture every segment of the shot list from the real, built page, one still per page frame (deterministic: no recording of Play).

    capture.py BASE_URL CAP_DIR {16x9|9x16}

The recipe is web/README.md's: open /?clip=<id>&f=<n>, move the Frame slider, wait until all three videos have finished seeking to the
middle of the frame (!seeking, readyState >= 2, currentTime == (n + 0.5) / 24), then shoot the segment's region. The page is not
modified except by what a reader can do (the Bare switch, the table's sort, the relief's drag and its "Orbit" tap) and two film-only
things: the dream pane made invisible for the opening beat, and CSS transitions switched off so a still never catches one mid-way.
"""
import asyncio, json, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shots, timeline
from playwright.async_api import async_playwright

base, cap_dir, aspect = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
BUILD = sys.argv[4] if len(sys.argv) > 4 else "dev"   # an id for the page build the stills come from (make-film.sh passes the dist hash)
VW, VH = shots.VIEWPORT[aspect]
FPS = 24
# third-party notices the page's own tests already allow (web/e2e/helpers.ts KNOWN_NOISE): three 0.186 and r3f 9.8 on the Clock; headless GL on ReadPixels
import re
NOISE = re.compile(r"THREE\.Clock: This module has been deprecated|GL Driver Message|GPU stall due to ReadPixels|Download the React DevTools")


def frames_needed(seg):
    kf = seg["frames"]
    lo, hi = min(f for _, f in kf), max(f for _, f in kf)
    return list(range(math.floor(lo), math.ceil(hi) + 1))


def yaw_grid(seg):
    if not seg.get("yaw"):
        return []
    a, b = (y for _, y in (seg["yaw"][0], seg["yaw"][-1]))
    return [round(k * shots.YAW_STEP, 4) for k in range(math.ceil(min(a, b) / shots.YAW_STEP), math.floor(max(a, b) / shots.YAW_STEP) + 1)]


async def settle(page):
    await page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")


async def wait_frame(page, f):
    await page.wait_for_function("""([f, fps]) => { const v = [...document.querySelectorAll('video')];
        return v.length === 3 && v.every(x => x.readyState >= 2 && !x.seeking && Math.abs(x.currentTime - (f + 0.5) / fps) < 1e-3); }""", arg=[f, FPS], timeout=30000)
    await settle(page)
    await page.wait_for_timeout(40)


async def main():
    tl = timeline.build(aspect)
    segs = shots.segments(aspect, tl)
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = await browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=1, color_scheme=shots.SCHEME[aspect])
        # a reader who has said "Not now" to the plain-words invite (for this visit): the invite is not part of the film's first screen
        await ctx.add_init_script("try { sessionStorage.setItem('dt-plain-later', '1'); } catch (e) {}")
        console = []
        for seg in segs:
            out = shots.seg_dir(cap_dir, seg, aspect, BUILD)
            out.mkdir(parents=True, exist_ok=True)
            fr = frames_needed(seg)
            yaws = yaw_grid(seg)
            todo = [f for f in fr if not (out / f"f{f:04d}.jpg").exists()] if not yaws else []
            todo_y = [y for y in yaws if not (out / f"y{y:+07.2f}.jpg").exists()]
            if not todo and not todo_y:
                print(f"[{aspect}] {seg['id']}: cached", flush=True); continue
            # a new context per segment at its own density
            c2 = await browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=seg["dsf"], color_scheme=shots.SCHEME[aspect])
            await c2.add_init_script("try { sessionStorage.setItem('dt-plain-later', '1'); } catch (e) {}")
            page = await c2.new_page()
            page.on("console", lambda m: console.append(f"{seg['id']} {m.type}: {m.text}") if m.type in ("error", "warning") and not NOISE.search(m.text) else None)
            page.on("pageerror", lambda e: console.append(f"{seg['id']} pageerror: {e}"))
            f0 = (todo or [fr[0]])[0]
            await page.goto(f"{base}/?clip={seg['clip']}&f={f0}")
            await page.wait_for_function("document.fonts.ready.then(() => true)")
            await page.wait_for_selector("video")
            if seg["view"] == "bare":
                await page.locator("label.seg-opt", has_text="Bare").click()
            css = "header { position: relative !important; }  /* the sticky bar would be drawn wherever a tall screenshot happens to scroll */ " + "*, *::before, *::after { transition: none !important; animation: none !important; scroll-behavior: auto !important; caret-color: transparent !important; }"
            css += "".join(f"{s} {{ visibility: hidden !important; }}" for s in seg.get("hide", []))
            await page.add_style_tag(content=css)
            await wait_frame(page, f0)
            slider = page.get_by_role("slider", name="Frame")
            r = seg["region"]
            clip = {"x": r[0], "y": r[1], "width": r[2], "height": r[3]}

            async def shoot(path):
                await page.evaluate("() => { const a = document.activeElement; if (a && a !== document.body) a.blur(); }")
                await page.mouse.move(VW - 2, VH - 2)
                await page.screenshot(path=str(path), clip=clip, full_page=True, type="jpeg", quality=94)

            if seg.get("sort"):
                # the header is visually hidden on a phone (rows are cards there), but the sort is the page's own: press it as the table's button would be
                await page.evaluate("() => [...document.querySelectorAll('.th-btn')].find(b => b.textContent.trim().startsWith('Departure')).click()")
                await page.mouse.move(VW - 2, VH - 2)
            if todo:
                for f in todo:
                    await slider.fill(str(f))
                    await wait_frame(page, f)
                    await shoot(out / f"f{f:04d}.jpg")
                print(f"[{aspect}] {seg['id']}: {len(todo)} frames", flush=True)
            if yaws:
                await slider.fill(str(int(seg["frames"][0][1])))
                await wait_frame(page, int(seg["frames"][0][1]))
                await page.locator(".relief-frame").scroll_into_view_if_needed()   # the atlases load only once the panel is near the screen
                if seg.get("arm"):
                    await page.get_by_role("button", name="Orbit the surfaces").click()
                await page.locator(".relief-frame canvas").wait_for(timeout=30000)
                await page.wait_for_timeout(800)
                box = await page.locator(".relief-frame").bounding_box()
                # the capture region is in page coordinates; the drag works in viewport coordinates
                sy = await page.evaluate("scrollY")
                cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                await page.mouse.move(cx, cy)
                await page.mouse.down()
                for y in yaws:
                    await page.mouse.move(cx + y / 0.15, cy, steps=6)   # the page turns 0.15 degrees a pixel, easing over about 240 ms
                    await page.wait_for_timeout(700)
                    await page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                    await page.screenshot(path=str(out / f"y{y:+07.2f}.jpg"), clip=clip, full_page=True, type="jpeg", quality=94)
                await page.mouse.up()
                print(f"[{aspect}] {seg['id']}: {len(yaws)} angles", flush=True)
            await c2.close()
        await ctx.close()
        await browser.close()
    (cap_dir / "console.json").write_text(json.dumps(console))
    print(f"[{aspect}] console: {console or 'clean'}")


asyncio.run(main())
