---
name: explainer-video
description: Generate bespoke 3b1b-style explainer videos on any topic — Manim CE animations with synced voiceover narration (local Kokoro TTS by default, ElevenLabs if ELEVENLABS_API_KEY is set). Use when asked to create an explainer video, animated math/CS visualization, narrated video, or "3blue1brown style" content.
---

# Explainer videos: Manim + TTS, fully local

Everything is installed and verified on this machine: `manim` (Manim Community,
via `uv tool install manim`), LaTeX, ffmpeg, and Kokoro TTS model weights in
`models/` beside this file. No API keys needed. Rendering a 20s 720p narrated
video takes ~2 minutes.

Setup check (fresh machine): if `models/` is missing beside this file, run
`./download-models.sh` (~338MB, idempotent). If `manim` is missing:
`uv tool install manim` (needs texlive + ffmpeg from pacman).

## Pipeline

Work in a scratch dir (e.g. `/tmp/explainer-<topic>/`). Deliver the final mp4
path to the user at the end.

### 1. Storyboard

Write the narration first, visuals second. Break the topic into 3–8 scenes;
each scene is one narration paragraph (1–3 sentences, spoken-register prose —
no markdown, spell out symbols: "e to the i pi", not `e^{iπ}`) plus a visual
idea. Save as `script.json`:

```json
{"voice": "am_michael", "speed": 1.0,
 "scenes": [
   {"name": "s1", "text": "Meet Euler's identity..."},
   {"name": "s2", "text": "It links five constants..."}
 ]}
```

Good Kokoro voices: `am_michael` (male, calm — closest to 3b1b), `af_heart`
(female, warm), `bm_george` (British male). If `ELEVENLABS_API_KEY` is set in
the environment, `voice` is an ElevenLabs voice id instead (default George).

### 2. Audio — generate BEFORE the video

Audio durations drive the animation timing, so always render audio first:

```bash
uv run --with kokoro-onnx --with soundfile <skill-dir>/tts.py script.json audio/
```

Writes `audio/<name>.wav` per scene and `audio/durations.json` ({name: seconds}).

### 3. Manim scene

Write one `Scene` class whose `construct` plays the scenes in order. Load
`audio/durations.json` and make each scene's total play+wait time equal its
narration duration:

```python
import json
from manim import *
D = json.load(open("audio/durations.json"))

class Video(Scene):
    def construct(self):
        # scene s1: animations totalling ~3s, then pad to narration length
        ...
        self.play(Write(eq), run_time=2)
        self.play(FadeIn(title), run_time=1)
        self.wait(max(D["s1"] - 3, 0.5))
        # transition into s2 counts against s2's budget...
```

3b1b style notes: dark background (manim default), `MathTex` for equations,
`ComplexPlane`/`NumberPlane` for geometry, `ValueTracker` + `always_redraw`
for continuous motion, `LaggedStart` for staggered reveals, YELLOW/BLUE/GREEN
accent colors, keep each visual sparse — one idea on screen at a time.

Render (`-qm` = 720p30; `-qh` = 1080p60 for final delivery):

```bash
manim -qm video.py Video
```

Output lands in `media/videos/video/720p30/Video.mp4`.

### 4. Mux

```bash
<skill-dir>/mux.sh media/videos/video/720p30/Video.mp4 final.mp4 audio/s1.wav audio/s2.wav ...
```

Pass wavs in scene order. Verify: video and audio durations should match
within ~2s; if audio is longer, a scene's waits don't cover its narration —
fix the `wait()` padding and re-render.

## Iterating

- Manim errors are almost always LaTeX (escape backslashes in `MathTex`
  raw strings) or overlapping mobjects — `FadeOut` the previous scene's
  objects before building the next.
- To preview a single scene cheaply, render with `-ql` (480p15) first.
- Narration too fast/slow: adjust `speed` in script.json (0.85–1.1 range),
  regenerate audio, re-render video (timings changed).
