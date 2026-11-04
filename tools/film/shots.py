"""The shot list as data: for each aspect, the segments the film is built from (script: film/script.md).

A segment is one stretch of picture from one page state:
  clip, view ("heat" | "bare"), hide (selectors made invisible, so a pane can "join"), frames (keyframes [(t, page frame)], linear;
  a float is blended between the two frames either side), region (the part of the page captured, CSS px) and dsf (its pixel density),
  cam (keyframes [(t, [x, y, w])] of the window the camera shows; smoothstep between them; h follows the output's aspect),
  yaw (keyframes [(t, degrees)]: the relief is dragged to each angle on a 1.25-degree grid), sort (a table header to click first),
  arm (tap "Orbit the surfaces" first: on a phone the relief is a still until tapped), fade (seconds the segment dissolves in).
Times are film seconds, from timeline.py. The picture follows the voice.
"""
FILM = "freshwater-basicEnhance__gen45__N__5s"       # the film's clip (hub call 81)
GREY = "saltwater-pellets__gen45__N__5s"             # a clip that runs past its check: the real pane turns grey at f20
DREAM = '[data-pane="dream"]'
UNSEEN = [DREAM, ".bare-note"]               # what is not there yet while the real pane is alone (the Bare note belongs to the dream)
YAW_STEP = 1.25

WINDOW = {"16x9": (1920, 1080), "9x16": (1080, 1670)}   # output px of the picture; 9:16 keeps 250 px under it for the caption band
VIEWPORT = {"16x9": (1920, 1080), "9x16": (390, 693)}   # CSS px
SCHEME = {"16x9": "light", "9x16": "dark"}


def seg_dir(cap_dir, seg, aspect, build_id):
    """A segment's stills live under a hash of what makes them what they are (page build, clip, view, region, density, what is hidden,
    sorted, armed): change any and the old stills are simply not looked at again, so nothing has to be deleted."""
    import hashlib, json
    key = json.dumps([build_id, aspect, VIEWPORT[aspect], seg["clip"], seg["view"], seg.get("hide", []), seg["region"], seg["dsf"], seg.get("sort"), seg.get("arm", False), YAW_STEP, "header-in-flow" if aspect == "9x16" else ""])
    return cap_dir / f"{seg['id']}-{hashlib.sha1(key.encode()).hexdigest()[:8]}"


def segments(aspect, tl):
    sh = {s["i"]: s for s in tl["shots"]}
    cap = {L["i"]: L["captions"] for L in tl["lines"]}
    S = lambda i: sh[i]["t0"]
    E = lambda i: sh[i]["t1"]
    seg = []
    if aspect == "16x9":
        full = [0, 0, 1920, 1080]
        # 1: the real pane alone, a slow push; then the dream joins (Bare)
        j = cap[1][1]["t0"] - 0.2
        # the camera pushes in on the real pane (the left of the stage), then draws back to take in both panes as the dream joins
        push = [(0, [0, 0, 1920]), (j, [24, 96, 1500]), (E(1) - 0.9, [24, 132, 1872])]
        tall = [0, 0, 1920, 1250]
        seg.append(dict(id="s1a", shot=1, t0=S(1), t1=j + 0.6, clip=FILM, view="bare", hide=UNSEEN, frames=[(0, 0)], region=tall, dsf=2, cam=push))
        seg.append(dict(id="s1b", shot=1, t0=j, t1=E(1), clip=FILM, view="bare", frames=[(0, 0)], region=tall, dsf=2, cam=push, fade=0.5))
        # 2: both panes play f0-f60, heat off
        seg.append(dict(id="s2", shot=2, t0=S(2), t1=E(2), clip=FILM, view="bare", frames=[(S(2) + 0.2, 0), (E(2) - 0.3, 60)], region=full, dsf=1))
        # 3: a clip that runs past its check: the real pane turns grey (f20) and the page says so
        seg.append(dict(id="s3", shot=3, t0=S(3), t1=E(3), clip=GREY, view="bare", frames=[(S(3) + 0.3, 13), (cap[3][0]["t1"] - 0.6, 26), (E(3) - 0.3, 36)], region=full, dsf=1))
        # 4: back on the film's clip, heat on, f40-f72, the key strip in view
        seg.append(dict(id="s4", shot=4, t0=S(4), t1=E(4), clip=FILM, view="heat", frames=[(S(4) + 0.2, 40), (E(4) - 0.4, 72)], region=full, dsf=1))
        # 5: the scrubber close; the cursor walks the D curve toward the gold
        c = cap[5]
        seg.append(dict(id="s5", shot=5, t0=S(5), t1=E(5), clip=FILM, view="heat",
                        frames=[(S(5) + 0.1, 10), (c[1]["t0"], 36), (c[2]["t0"], 62), (c[2]["t0"] + 1.3, 76), (c[2]["t0"] + 2.3, 90), (E(5), 92)],
                        region=full, dsf=2, cam=[(0, [640, 190, 1280])]))
        # 6: f72-f105, the heat flares, the curve turns gold; the camera goes down to the plan view's path
        c = cap[6]
        seg.append(dict(id="s6", shot=6, t0=S(6), t1=E(6), clip=FILM, view="heat",
                        frames=[(S(6) + 0.4, 72), (c[0]["t1"] + 0.6, 105)], region=[0, 0, 1920, 1700], dsf=1,
                        cam=[(0, [0, 0, 1920]), (c[0]["t0"] + 2.2, [0, 0, 1920]), (c[0]["t1"] + 0.6, [0, 360, 1920])]))
        # 7: the table sorted by departure (three rows lead), then the relief turning slowly
        c = cap[7]
        seg.append(dict(id="s7a", shot=7, t0=S(7), t1=c[1]["t0"] + 0.4, clip=FILM, view="heat", frames=[(0, 105)], sort="departure",
                        region=[0, 2600, 1920, 1250], dsf=1, cam=[(0, [0, 2606, 1920]), (c[1]["t0"], [0, 2640, 1920])]))
        seg.append(dict(id="s7b", shot=7, t0=c[1]["t0"], t1=E(7), clip=FILM, view="heat", frames=[(0, 105)], fade=0.4,
                        region=[650, 1050, 620, 440], dsf=3.5, cam=[(0, [670, 1095, 580])],
                        yaw=[(c[1]["t0"] + 0.2, -21.25), (E(7) - 0.3, 21.25)]))
        # 8: the whole first screen at f105
        seg.append(dict(id="s8", shot=8, t0=S(8), t1=E(8), clip=FILM, view="heat", frames=[(0, 105)], region=full, dsf=2,
                        cam=[(0, [40, 23, 1840]), (E(8), [0, 0, 1920])]))
    else:
        full = [0, 332, 390, 2250]
        stage = 348          # the real pane's top edge (page y), the window's top
        # 1: the real pane alone, a slow push; then the dream joins
        j = cap[1][1]["t0"] - 0.2
        push = [(0, [0, stage, 390]), (E(1), [20, stage + 6, 350])]
        r = [0, 332, 390, 640]
        seg.append(dict(id="s1a", shot=1, t0=S(1), t1=j + 0.6, clip=FILM, view="bare", hide=UNSEEN, frames=[(0, 0)], region=r, dsf=3.5, cam=push))
        seg.append(dict(id="s1b", shot=1, t0=j, t1=E(1), clip=FILM, view="bare", frames=[(0, 0)], region=r, dsf=3.5, cam=push, fade=0.5))
        seg.append(dict(id="s2", shot=2, t0=S(2), t1=E(2), clip=FILM, view="bare", frames=[(S(2) + 0.2, 0), (E(2) - 0.3, 60)], region=r, dsf=2.7692, cam=[(0, [0, stage, 390])]))
        seg.append(dict(id="s3", shot=3, t0=S(3), t1=E(3), clip=GREY, view="bare", frames=[(S(3) + 0.3, 13), (cap[3][0]["t1"] - 0.6, 26), (E(3) - 0.3, 36)], region=r, dsf=2.7692, cam=[(0, [0, stage, 390])]))
        # 4 and 5 share the lower window: the dream pane's foot, the scrubber and the key strip
        low = 684
        r45 = [0, 640, 390, 720]
        seg.append(dict(id="s4", shot=4, t0=S(4), t1=E(4), clip=FILM, view="heat", frames=[(S(4) + 0.2, 40), (E(4) - 0.4, 72)], region=[0, 332, 390, 960], dsf=2.7692,
                        cam=[(0, [0, stage, 390]), (cap[4][0]["t1"] - 1.2, [0, stage, 390]), (cap[4][0]["t1"], [0, low, 390])]))
        c = cap[5]
        seg.append(dict(id="s5", shot=5, t0=S(5), t1=E(5), clip=FILM, view="heat",
                        frames=[(S(5) + 0.1, 10), (c[1]["t0"], 36), (c[2]["t0"], 62), (c[2]["t0"] + 1.3, 76), (c[2]["t0"] + 2.3, 90), (E(5), 92)],
                        region=[0, 332, 390, 960], dsf=2.7692, cam=[(0, [0, low, 390])]))
        # 6: the flare on the stage, then the numbers (V 1.00), then the plan view
        c = cap[6]
        seg.append(dict(id="s6", shot=6, t0=S(6), t1=E(6), clip=FILM, view="heat", frames=[(S(6) + 0.4, 72), (c[0]["t1"] + 0.6, 105)],
                        region=full, dsf=2.7692,
                        cam=[(0, [0, low, 390]), (S(6) + 1.4, [0, stage, 390]), (c[1]["t0"] - 0.3, [0, stage, 390]), (c[1]["t0"] + 0.8, [0, 1316, 390]),
                             (c[2]["t0"] - 0.2, [0, 1316, 390]), (c[2]["t0"] + 1.0, [0, 1930, 390])]))
        # 7: the table sorted by departure, then the relief (armed: a tap on a phone) turning slowly
        c = cap[7]
        seg.append(dict(id="s7a", shot=7, t0=S(7), t1=c[1]["t0"] + 0.4, clip=FILM, view="heat", frames=[(0, 105)], sort="departure",
                        region=[0, 4240, 390, 900], dsf=2.7692, cam=[(0, [0, 4270, 390])]))
        seg.append(dict(id="s7b", shot=7, t0=c[1]["t0"], t1=E(7), clip=FILM, view="heat", frames=[(0, 105)], fade=0.4, arm=True,
                        region=[0, 2380, 390, 700], dsf=2.7692, cam=[(0, [0, 2402, 390])],
                        yaw=[(c[1]["t0"] + 0.2, -21.25), (E(7) - 0.3, 21.25)]))
        # 8: the stage at f105 (on a phone the first screen is the title and the pickers; the stage is the whole first screen that matters)
        seg.append(dict(id="s8", shot=8, t0=S(8), t1=E(8), clip=FILM, view="heat", frames=[(0, 105)], region=[0, 332, 390, 700], dsf=2.7692,
                        cam=[(0, [0, stage, 390])]))
    return seg
