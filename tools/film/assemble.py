#!/usr/bin/env python3
"""Build one cut from a capture dir: composite every 24 fps frame (camera, slow-motion blend, dissolves, caption band), mix the
narration, normalise loudness, encode, and make the poster and the contact sheet.

    assemble.py CAP_DIR OUT_DIR {16x9|9x16}

Picture. Each segment (shots.py) is a stack of stills, one per page frame; a frame position between two integers is a blend of the
two (the slow-motion the narration needs: a 5 s clip is stretched to a line of speech). The camera is a crop window over the still,
eased between keyframes; the crop is resampled once, with Lanczos, straight from the capture's own pixels.
Sound. The nine reads, each at its line's start, nothing else: the gaps are silence. One linear gain takes the integrated loudness
to -16 LUFS; a limiter only if the true peak would pass -1.5 dBTP (the AAC re-encode adds a little); the finished file is measured again.
"""
import functools, json, math, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shots, timeline
from PIL import Image
from playwright.sync_api import sync_playwright

cap_dir, out_dir, aspect = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
BUILD = sys.argv[4] if len(sys.argv) > 4 else "dev"
ROOT = Path(__file__).resolve().parents[2]
CFG = timeline.CFG
FPS = timeline.FPS
W, WH = shots.WINDOW[aspect]
CW, CH = (1920, 1080) if aspect == "16x9" else (1080, 1920)
BAND_H = 112 if aspect == "16x9" else 250
INK, GOLD = "#1c1915", "#d6a43c"
tl = timeline.build(aspect)
segs = shots.segments(aspect, tl)
TOTAL = tl["total"]
NAME = f"divetwin-{aspect}"
FONT = ROOT / "web/public/fonts/geist-latin.woff2"
smooth = lambda u: u * u * (3 - 2 * u)


def run(*a, **k):
    return subprocess.run([str(x) for x in a], check=True, capture_output=True, text=True, **k)


# ---------------------------------------------------------------- captions and the end card (HTML, shot with Geist)
def html_assets():
    work = cap_dir / "text"
    work.mkdir(exist_ok=True)
    face = f"@font-face {{ font-family: 'Geist'; src: url('file://{FONT}') format('woff2'); font-weight: 400 800; }}"
    cap_px = 32 if aspect == "16x9" else 42
    pad = 140 if aspect == "16x9" else 64
    page = f"""<!doctype html><meta charset=utf-8><style>{face}
      html,body {{ margin:0; background:transparent; }}
      #band {{ width:{CW}px; height:{BAND_H}px; box-sizing:border-box; padding:0 {pad}px; display:flex; align-items:center; justify-content:{'center' if aspect == '16x9' else 'flex-start'};
               background:{'rgba(16,14,11,0.9)' if aspect == '16x9' else '#14110e'}; color:#fff; font:500 {cap_px}px/1.3 'Geist', sans-serif; letter-spacing:-0.005em; }}
      #t {{ margin:0; max-width:{CW - 2 * pad}px; text-wrap:{'balance' if aspect == '16x9' else 'pretty'}; {'text-align:center;' if aspect == '16x9' else ''} font-feature-settings:'tnum' 0; }}
      #card {{ width:{CW}px; height:{CH}px; background:{INK}; color:#ecebe6; box-sizing:border-box; display:flex; flex-direction:column; justify-content:center; padding:0 {pad if aspect=='16x9' else 80}px; font-family:'Geist',sans-serif; position:relative; }}
      #card h1 {{ margin:0; font-weight:700; font-size:{150 if aspect == '16x9' else 168}px; letter-spacing:-0.03em; line-height:1; color:#fff; }}
      #card .rule {{ width:{120 if aspect=='16x9' else 96}px; height:6px; background:{GOLD}; margin:{40 if aspect=='16x9' else 48}px 0; }}
      #card .url {{ font-size:{44 if aspect == '16x9' else 46}px; font-weight:500; color:{GOLD}; margin:0; }}
      #card .by {{ font-size:{32 if aspect == '16x9' else 36}px; color:#b3aa9e; margin:14px 0 0; }}
      #card .disc {{ position:absolute; left:{pad if aspect=='16x9' else 80}px; right:{pad if aspect=='16x9' else 80}px; bottom:{56 if aspect=='16x9' else 90}px; font-size:{22 if aspect == '16x9' else 26}px; line-height:1.4; color:#9c9488; margin:0; }}
    </style><body><div id=band><p id=t></p></div><div id=card><h1>Dive Twin</h1><div class=rule></div><p class=url>divetwin.studionephele.com</p><p class=by>Studio Nephele</p>
    <p class=disc>{CFG['disclosure']}</p></div>"""
    f = work / "text.html"
    f.write_text(page)
    caps = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": CW, "height": CH})
        pg.goto(f"file://{f}")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_function("document.fonts.check(\"500 32px Geist\")")
        for L in tl["lines"]:
            if L["i"] == len(tl["lines"]):
                continue
            for k, c in enumerate(L["captions"]):
                pg.evaluate("t => { document.getElementById('card').style.display='none'; document.getElementById('band').style.display='flex'; document.getElementById('t').textContent = t; }", c["text"])
                over = pg.evaluate("() => { const t = document.getElementById('t'), b = document.getElementById('band'); return t.getBoundingClientRect().height > b.clientHeight - 24; }")
                if over:
                    sys.exit(f"caption overflows its band: {c['text']}")
                path = work / f"cap-{L['i']}-{k}.png"
                pg.locator("#band").screenshot(path=str(path), omit_background=True)
                caps[(L["i"], k)] = path
        pg.evaluate("() => { document.getElementById('band').style.display='none'; document.getElementById('card').style.display='flex'; }")
        pg.wait_for_timeout(100)
        pg.locator("#card").screenshot(path=str(work / "card.png"))
        pg.evaluate("document.getElementById('t').textContent=''; document.getElementById('card').style.display='none'; document.getElementById('band').style.display='flex'")
        pg.locator("#band").screenshot(path=str(work / "band-empty.png"), omit_background=True)
        b.close()
    return {k: Image.open(v).convert("RGBA") for k, v in caps.items()}, Image.open(work / "card.png").convert("RGB"), Image.open(work / "band-empty.png").convert("RGBA")


CAPS, CARD, BAND = html_assets()


# ---------------------------------------------------------------- the picture
@functools.lru_cache(maxsize=48)
def load(path):
    return Image.open(path).convert("RGB")


def interp(kf, t):
    if t <= kf[0][0]:
        return kf[0][1]
    for (t0, a), (t1, b) in zip(kf, kf[1:]):
        if t <= t1:
            return a + (b - a) * (t - t0) / (t1 - t0) if t1 > t0 else b
    return kf[-1][1]


def cam_at(seg, t):
    kf = seg.get("cam") or [(0, [seg["region"][0], seg["region"][1], seg["region"][2]])]
    if t <= kf[0][0]:
        return kf[0][1]
    for (t0, a), (t1, b) in zip(kf, kf[1:]):
        if t <= t1:
            u = smooth((t - t0) / (t1 - t0)) if t1 > t0 else 1
            return [a[k] + (b[k] - a[k]) * u for k in range(3)]
    return kf[-1][1]


def crop(img, seg, t):
    x, y, w = cam_at(seg, t)
    h = w * WH / W
    r = seg["region"]
    d = seg["dsf"]
    box = ((x - r[0]) * d, (y - r[1]) * d, (x - r[0] + w) * d, (y - r[1] + h) * d)
    if box[0] < -0.5 or box[1] < -0.5 or box[2] > img.width + 0.5 or box[3] > img.height + 0.5:
        raise SystemExit(f"{seg['id']}: camera window {box} leaves the captured region {img.size} at t={t:.2f}")
    return img.resize((W, WH), Image.LANCZOS, box=box)


def render_seg(seg, t):
    d = seg["dir"]
    if seg.get("yaw"):
        kf = seg["yaw"]
        u = smooth(min(max((t - kf[0][0]) / (kf[-1][0] - kf[0][0]), 0), 1))
        yaw = kf[0][1] + (kf[-1][1] - kf[0][1]) * u
        g = yaw / shots.YAW_STEP
        lo, hi = math.floor(g), math.ceil(g)
        a = crop(load(str(d / f"y{lo * shots.YAW_STEP:+07.2f}.jpg")), seg, t)
        if hi == lo:
            return a
        b = crop(load(str(d / f"y{hi * shots.YAW_STEP:+07.2f}.jpg")), seg, t)
        return Image.blend(a, b, g - lo)
    pos = interp([(tt, float(f)) for tt, f in seg["frames"]], t) if len(seg["frames"]) > 1 else float(seg["frames"][0][1])
    lo = math.floor(pos + 1e-9)
    hi = math.ceil(pos - 1e-9)
    a = crop(load(str(d / f"f{lo:04d}.jpg")), seg, t)
    if hi == lo:
        return a
    return Image.blend(a, crop(load(str(d / f"f{hi:04d}.jpg")), seg, t), pos - lo)


for s in segs:
    s["dir"] = shots.seg_dir(cap_dir, s, aspect, BUILD)
S9 = tl["shots"][-1]["t0"]
CARD_FADE = 0.5


def picture(t):
    last = segs[-1]
    tt = min(t, last["t1"])
    base = None
    for s in segs:
        if s["t0"] <= tt < s["t1"] or (s is last and tt >= s["t1"]):
            im = render_seg(s, min(t, s["t1"]))
            a = 1.0 if base is None or not s.get("fade") else min(max((tt - s["t0"]) / s["fade"], 0), 1)
            base = im if base is None or a >= 1 else Image.blend(base, im, a)
    return base


def caption_for(t):
    for L in tl["lines"][:-1]:
        for k, c in enumerate(L["captions"]):
            if c["t0"] <= t < c["t1"]:
                return CAPS[(L["i"], k)]
    return BAND


def frame_at(t, captions=True):
    pic = picture(t)
    if t >= S9:
        u = min((t - S9) / CARD_FADE, 1)
        return Image.blend(pic.resize((CW, CH)) if pic.size != (CW, CH) else pic, CARD, smooth(u)) if aspect == "16x9" else Image.blend(canvas_of(pic, False), CARD, smooth(u))
    if aspect == "16x9":
        if captions:
            pic = pic.convert("RGBA")
            pic.alpha_composite(caption_for(t), (0, CH - BAND_H))
            pic = pic.convert("RGB")
        return pic
    return canvas_of(pic, captions, t)


def canvas_of(pic, captions=True, t=0.0):
    c = Image.new("RGB", (CW, CH), "#14110e")
    c.paste(pic, (0, 0))
    if captions:
        c.paste(caption_for(t).convert("RGB"), (0, WH))
    return c


# ---------------------------------------------------------------- sound
def mix_audio(path):
    ins, fil = [], []
    for k, L in enumerate(tl["lines"]):
        ins += ["-i", str(timeline.VO / L["file"])]
        fil.append(f"[{k}:a]adelay={int(round(L['start'] * 1000))}:all=1[a{k}]")
    n = len(tl["lines"])
    graph = ";".join(fil) + ";" + "".join(f"[a{k}]" for k in range(n)) + f"amix=inputs={n}:normalize=0,apad=whole_dur={TOTAL},atrim=0:{TOTAL},aresample=48000[m]"
    run("ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", graph, "-map", "[m]", "-ac", "1", "-ar", 48000, path)


def measure(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    tail = r[r.rfind("Summary:"):]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", tail).group(1)), float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail).group(1))


def main():
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = cap_dir / "voice_raw.wav"
    mix_audio(raw)
    i_lufs, tp = measure(raw)
    gain = -16.0 - i_lufs
    af = f"volume={gain:.3f}dB"
    if tp + gain > -1.5:
        af += f",alimiter=limit={10 ** (-1.5 / 20):.4f}:level=disabled"
    norm = cap_dir / "voice_norm.wav"
    run("ffmpeg", "-y", "-v", "error", "-i", raw, "-af", af, "-ar", 48000, "-ac", 1, norm)
    # the video: every frame composited and piped to x264 (BT.709, limited range)
    n = int(round(TOTAL * FPS))
    vid = cap_dir / "video.mp4"
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{CW}x{CH}", "-r", str(FPS), "-i", "-",
                            "-vf", "scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "20",
                            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", "-r", str(FPS), str(vid)], stdin=subprocess.PIPE)
    for k in range(n):
        enc.stdin.write(frame_at(k / FPS).tobytes())
        if k % 240 == 0:
            print(f"[{aspect}] frame {k}/{n}", flush=True)
    enc.stdin.close()
    if enc.wait():
        sys.exit("x264 failed")
    mp4 = out_dir / f"{NAME}.mp4"

    def mux(wav):
        run("ffmpeg", "-y", "-v", "error", "-i", vid, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", "aformat=channel_layouts=stereo",
            "-c:a", "aac", "-b:a", "192k", "-ar", 48000, "-t", f"{TOTAL:.4f}", "-movflags", "+faststart", mp4)
        return measure(mp4)

    fi, ftp = mux(norm)
    if abs(fi + 16.0) > 0.1:   # the stereo down/up-mix and the AAC pass move it a little: one correction, then measure again
        gain2 = gain + (-16.0 - fi)
        af2 = f"volume={gain2:.3f}dB" + (f",alimiter=limit={10 ** (-1.5 / 20):.4f}:level=disabled" if tp + gain2 > -1.5 else "")
        norm2 = cap_dir / "voice_norm2.wav"
        run("ffmpeg", "-y", "-v", "error", "-i", raw, "-af", af2, "-ar", 48000, "-ac", 1, norm2)
        fi, ftp = mux(norm2)
    print(f"[{aspect}] narration {i_lufs:.2f} LUFS / {tp:.2f} dBFS before gain; final file {fi:.2f} LUFS, true peak {ftp:.2f} dBTP")
    # poster: the whole first screen at f105 (shot 8), no band; contact sheet: a frame every 3 s of the finished file
    frame_at(tl["shots"][7]["t0"] + 0.1, captions=False).save(out_dir / f"{NAME}-poster.png")
    tw, cols, rows = (480, 4, 6) if aspect == "16x9" else (270, 8, 3)
    run("ffmpeg", "-y", "-v", "error", "-i", mp4, "-vf", f"fps=1/3,scale={tw}:-1,tile={cols}x{rows}:padding=4:color=gray", "-frames:v", 1, out_dir / f"{NAME}-contact.png")
    # SRT sidecar from the caption chunks
    def ts(x):
        return f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d},{int(round((x % 1) * 1000)):03d}"
    srt, k = [], 1
    for L in tl["lines"]:
        for c in L["captions"]:
            srt.append(f"{k}\n{ts(c['t0'])} --> {ts(c['t1'])}\n{c['text']}\n"); k += 1
    (out_dir / f"{NAME}.srt").write_text("\n".join(srt))


main()
