# Sisyphus the Rat

A ~64s 2D animated short about an AI agent's life as a pet rat — hand-authored
as a single self-contained `index.html` (SVG vector scenes + JS timeline),
with a CI pipeline that renders it to a narrated MP4.

## Watch it

Open `index.html` in any browser. Space toggles play, the bar seeks,
♪ toggles the WebAudio blips. No dependencies, no build.

## Render an MP4 (cloud only)

The phone cannot run heavy renders, so the pipeline lives in GitHub Actions:

1. Go to **Actions → render → Run workflow** (accept default 24 fps).
2. Wait ~20–40 min.
3. Download the `rat-film-mp4` artifact → `rat.mp4` (1920×1080, H.264 + AAC,
   narration + ambient music, burned-in captions).

Pipeline: headless Chromium screenshots `index.html?render=1` at 24 fps
(1536 deterministic frames — every frame is `paint(t)`), `edge-tts` narrates
each caption line (rate auto-fitted to subtitle windows), a numpy-generated
ambient pad sits underneath, and ffmpeg mixes + muxes everything.

## Files

- `index.html` — the film (single file, plays anywhere)
- `render/render.js` — playwright frame capture
- `render/audio.py` — narration (edge-tts) + music (numpy) + mix/mux (ffmpeg)
- `.github/workflows/render.yml` — the CI render job
