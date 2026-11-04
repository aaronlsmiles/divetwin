# tools/film

The film (task 5.1). The script and shot list are `film/script.md` (binding words); this builds the cuts.

    tools/film/make-film.sh

It builds the page (`VITE_MEDIA_BASE=/media/`, so the real clips in `runs/assets` are served), serves it with `vite preview` on a free
port (never 5196 or 5199), captures every shot from the real page with Playwright, and assembles with ffmpeg. Outputs go to `film/out/`
(git-ignored):

- `divetwin-16x9.mp4` (1920 x 1080) and `divetwin-9x16.mp4` (1080 x 1920): H.264 24 fps, yuv420p, BT.709, +faststart, AAC 48 kHz, -16 LUFS integrated, true peak <= -1 dBTP (the voice only; the gaps are silence)
- `divetwin-*-poster.png` (the whole first screen at f105, no captions) and `divetwin-*-contact.png` (a frame every 3 s of the finished file)
- `divetwin-*.srt`, the caption chunks as a sidecar

It then copies the 16:9 cut into the page, at `web/public/film/` (tracked, unlike `film/out/`): `divetwin-16x9.mp4` as it is and
`divetwin-16x9-poster.jpg` (the poster as a JPEG, ffmpeg `-q:v 2`). The 9:16 cut stays local. Nothing here pushes or deploys, and the page
has no film section yet.

Needs node 22, Python 3 with Playwright (Chromium), Pillow, ffmpeg (no libass or freetype needed: captions are PNGs from an HTML page set in Geist).

## How it is made

- **Narration** (`voice.py`, `film.json`): the studio voice (Hume Octave, the voice id and acting direction of the StillDrawn explorer's films), the nine lines of the script read in ONE batch (989 characters; free tier). `film/vo/*.wav` is git-ignored (a paid read is not repeated: a line whose text, voice and direction are unchanged is never read again); `film/vo/lines.json` (ids, durations) is tracked. It runs under `op run --env-file=$HOME/projects/studio/tools/hume.env.op`, never prints the key, and without `--yes` only prints the character count. A retake of one line: `... voice.py --yes --retake N`. If Hume fails it stops: no other voice, no music.
- **The clock** (`timeline.py`): the voice sets the pace. Each line starts after the last one's own trailing silence plus 0.8 s (1.8 s after line 6, to look at the plan view), the picture of a shot starts 0.4 s before its line, the end card holds 2.6 s after the last word. Caption chunks are the sentences (a sentence over 150 characters at 16:9, 108 at 9:16, splits at a comma), timed by the pauses the read itself made.
- **The shots** (`shots.py`): the shot list as data. A segment is one page state, its region, the page frames it plays (keyframes in film time), and a camera window over the still.
- **Capture** (`capture.py`): web/README.md's deterministic recipe, never a recording of Play. Open `/?clip=<id>&f=<n>`, move the Frame slider, wait until all three videos have finished seeking to the middle of the frame (`!seeking`, `readyState >= 2`, `currentTime == (n + 0.5) / 24`), screenshot the region. The page is changed only by what a reader can do (the Bare switch, the table's Departure sort, the relief's drag, the "Orbit the surfaces" tap on a phone) and three film-only things: the invite is already put away ("Not now"), the dream pane is invisible for the opening beat so it can join, and CSS transitions are off. 16:9 is captured at a 1920 x 1080 viewport (light), 9:16 at the page's own 390 px phone layout at 2.77x (dark). Stills are cached under a hash of the page build and the segment (`film/.capture/<aspect>/<segment>-<hash>/`), so only a changed page or shot is captured again.
- **Assembly** (`assemble.py`): 24 fps frames composited in Pillow. A page frame position between two integers is a blend of the two stills (the slow motion that stretches a 5 s clip over a line of speech; it is slowed, not sped up, and not the page's Play); the camera is a Lanczos crop eased between keyframes; a segment can dissolve in. Captions are a dark band (Geist, white, sentence case) over the foot of the 16:9 frame and in the 250 px under the 9:16 picture. The end card carries the disclosure line from the script. The frames go to x264 (CRF 17, slow); one linear gain takes the voice to -16 LUFS, with a limiter only if the true peak would pass -1.5 dBTP; the finished file is measured again.

Check commands: `ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,pix_fmt,sample_rate,channels film/out/divetwin-16x9.mp4`; loudness `ffmpeg -i film/out/divetwin-16x9.mp4 -af ebur128=peak=true -f null -`; black frames `ffmpeg -i ... -vf blackdetect=d=0.1:pix_th=0.05 -an -f null -`.
