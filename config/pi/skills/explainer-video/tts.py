#!/usr/bin/env python3
"""Per-scene TTS for explainer videos.

Usage:
    uv run --with kokoro-onnx --with soundfile tts.py script.json outdir/

script.json format:
    {"voice": "am_michael", "speed": 1.0,
     "scenes": [{"name": "s1", "text": "Narration for scene one."}, ...]}

Writes outdir/<name>.wav per scene and outdir/durations.json
({name: seconds}). If ELEVENLABS_API_KEY is set, uses ElevenLabs
instead of local Kokoro (voice field is then an ElevenLabs voice id,
default "JBFqnCBsd6RMkjVDRZzb").
"""
import json
import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent


def tts_kokoro(scenes, voice, speed, outdir):
    import soundfile as sf
    from kokoro_onnx import Kokoro

    k = Kokoro(
        str(SKILL_DIR / "models/kokoro-v1.0.onnx"),
        str(SKILL_DIR / "models/voices-v1.0.bin"),
    )
    durs = {}
    for s in scenes:
        samples, sr = k.create(s["text"], voice=voice or "am_michael", speed=speed)
        sf.write(outdir / f"{s['name']}.wav", samples, sr)
        durs[s["name"]] = len(samples) / sr
    return durs


def tts_elevenlabs(scenes, voice, outdir):
    import subprocess
    import urllib.request

    key = os.environ["ELEVENLABS_API_KEY"]
    voice = voice or "JBFqnCBsd6RMkjVDRZzb"
    durs = {}
    for s in scenes:
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            data=json.dumps({"text": s["text"], "model_id": "eleven_multilingual_v2"}).encode(),
            headers={"xi-api-key": key, "Content-Type": "application/json"},
        )
        mp3 = outdir / f"{s['name']}.mp3"
        mp3.write_bytes(urllib.request.urlopen(req).read())
        wav = outdir / f"{s['name']}.wav"
        subprocess.run(["ffmpeg", "-y", "-i", str(mp3), str(wav)], capture_output=True, check=True)
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)],
            capture_output=True, text=True, check=True,
        )
        durs[s["name"]] = float(out.stdout.strip())
    return durs


def main():
    script = json.loads(Path(sys.argv[1]).read_text())
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    scenes = script["scenes"]
    voice = script.get("voice")
    if os.environ.get("ELEVENLABS_API_KEY"):
        durs = tts_elevenlabs(scenes, voice, outdir)
    else:
        durs = tts_kokoro(scenes, voice, script.get("speed", 1.0), outdir)
    (outdir / "durations.json").write_text(json.dumps(durs, indent=2))
    print(json.dumps(durs, indent=2))


if __name__ == "__main__":
    main()
