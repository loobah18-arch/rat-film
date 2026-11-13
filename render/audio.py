#!/usr/bin/env python3
"""
Audio pipeline for the rat-film MP4:
  1. Parse CAPS narration lines (start, end, text) directly from ../index.html
     — single source of truth with the burned-in subtitles.
  2. Synthesize each line with edge-tts (free, no API key), auto-fitting the
     read rate so every line fits inside its subtitle window.
  3. Generate a 64s ambient music bed with numpy (sine pads, slow LFO).
  4. Mix narration over music with ffmpeg -> audio.wav.
  5. Mux frames + audio -> rat.mp4 (H.264 yuv420p + AAC).
Usage: python render/audio.py   (env: FPS=24, DUR=64)
"""
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DUR = float(os.environ.get("DUR", "64"))
FPS = float(os.environ.get("FPS", "24"))
FRAMES_DIR = Path(os.environ.get("OUT", "frames"))
SR = 44100
VOICE = os.environ.get("VOICE", "en-US-ChristopherNeural")
WORK = Path("render/_work")
WORK.mkdir(parents=True, exist_ok=True)


def run(cmd, **kw):
    print("+", " ".join(map(str, cmd)))
    return subprocess.run(cmd, check=True, **kw)


def ffprobe_dur(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def caps_from_html():
    src = (ROOT / "index.html").read_text(encoding="utf-8")
    pat = re.compile(r"\[\s*([\d.]+),\s*([\d.]+),\s*\"(.+?)\"\s*\],")
    caps = [(float(a), float(b), t) for a, b, t in pat.findall(src)]
    if not caps:
        sys.exit("no CAPS found in index.html")
    return caps


def tts_lines(caps):
    """edge-tts per line; regenerate with faster rate until it fits the window."""
    wavs = []
    for i, (a, b, text) in enumerate(caps):
        window = b - a
        target = window - 0.45          # leave breathing room before next line
        out = WORK / f"n{i:02d}.mp3"
        rate = 0
        for _ in range(3):
            run(["edge-tts", "--voice", VOICE,
                 f"--rate={rate:+d}%", "--text", text, "--write-media", str(out)])
            d = ffprobe_dur(out)
            if d <= target:
                break
            rate = -int(round((d / target - 1) * 100)) - 4  # extra headroom
            print(f"  line {i}: {d:.2f}s > target {target:.2f}s, retry rate {rate:+d}%")
        wavs.append((a, out))
        print(f"  line {i}: {d:.2f}s in [{a:.2f}..{b:.2f}]  \"{text}\"")
    return wavs


def music_bed():
    """Soft ambient pad: Am-F-C-G, one chord per 8s, sine layers + slow LFO."""
    n = int(DUR * SR)
    t = np.arange(n) / SR
    chords = [
        (110.00, 130.81, 164.81),   # A2 C3 E3  (Am)
        (87.31, 110.00, 130.81),    # F2 A2 C3  (F)
        (130.81, 164.81, 196.00),   # C3 E3 G3  (C)
        (98.00, 123.47, 146.83),    # G2 B2 D3  (G)
    ]
    lfo = 0.85 + 0.15 * np.sin(2 * np.pi * 0.06 * t)
    mix = np.zeros(n)
    seg = 8.0
    for k in range(int(math.ceil(DUR / seg))):
        chord = chords[k % len(chords)]
        s0, s1 = int(k * seg * SR), min(int((k + 1) * seg * SR), n)
        if s0 >= n:
            break
        env = np.ones(s1 - s0)
        ramp = int(2.0 * SR)
        e = min(ramp, env.size // 2)
        env[:e] = 0.5 - 0.5 * np.cos(np.pi * np.arange(e) / e)
        env[-e:] = 0.5 + 0.5 * np.cos(np.pi * np.arange(e) / e)
        for f in chord:
            for mult, g in ((1, 1.0), (2, 0.45), (3, 0.22), (4, 0.10)):
                mix[s0:s1] += g * env * np.sin(2 * np.pi * f * mult * t[s0:s1])
        # low sub pulse on the chord root
        mix[s0:s1] += 0.5 * env * np.sin(2 * np.pi * chord[0] * 0.5 * t[s0:s1])
    mix *= lfo
    fade_in = int(2.0 * SR)
    fade_out = int(4.0 * SR)
    mix[:fade_in] *= np.linspace(0, 1, fade_in)
    mix[-fade_out:] *= np.linspace(1, 0, fade_out)
    mix *= 0.10
    # gentle stereo width via tiny detune
    d = int(0.012 * SR)
    left = mix
    right = np.roll(mix, d)
    stereo = np.stack([left, right], axis=1)
    stereo = np.clip(stereo, -1, 1)
    wav_path = WORK / "music.wav"
    import wave
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())
    return wav_path


def mix(wavs):
    """Music + narration at line starts -> audio.wav (48k stereo)."""
    music = music_bed()
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-i", str(music)]
    for _, p in wavs:
        cmd += ["-i", str(p)]
    fc = "[0:a]volume=1.0[m];"
    for i in range(len(wavs)):
        ms = int(wavs[i][0] * 1000)
        fc += f"[{i+1}:a]adelay={ms}|{ms},volume=1.7[n{i}];"
    fc += (f"[m][n0]" + "".join(f"[n{i}]" for i in range(1, len(wavs))) +
           f"amix=inputs={len(wavs)+1}:normalize=0:duration=first,"
           f"atrim=0:{DUR},asetpts=PTS-STARTPTS,alimiter=limit=0.97,"
           "aresample=48000[out]")
    cmd += ["-filter_complex", fc, "-map", "[out]",
            "-c:a", "pcm_s16le", "audio.wav"]
    run(cmd)


def mux():
    run(["ffmpeg", "-y", "-v", "error",
         "-framerate", str(int(FPS)),
         "-i", str(FRAMES_DIR / "f%05d.jpg"),
         "-i", "audio.wav",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart",
         "-shortest", "rat.mp4"])
    d = ffprobe_dur("rat.mp4")
    size = Path("rat.mp4").stat().st_size / 1e6
    print(f"rat.mp4: {d:.1f}s, {size:.1f} MB")


if __name__ == "__main__":
    caps = caps_from_html()
    wavs = tts_lines(caps)
    mix(wavs)
    mux()
