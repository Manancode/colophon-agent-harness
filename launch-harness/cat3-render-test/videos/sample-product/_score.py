#!/usr/bin/env python3
"""
8-dim gate P/M evidence collector for the cal.com render-engine render.

- Extracts timeline-ordered frames from renders/video.mp4 via ffmpeg.
- Samples each with Pillow (dominant colors, non-white %, near-black %,
  brand-color hits) — the P channel.
- Computes frame-to-frame mean-abs-diff for motion/dim-4 (crossfade vs hard cut).
- Runs ffprobe for the M channel (duration, streams, audio presence).
- Extracts the mixed audio and reports peak amplitude (dim-5 P evidence).

Run AFTER the render finishes:
  python3 _score.py
"""
import json, os, subprocess, sys
from collections import Counter
from PIL import Image

ROOT = "./cat3-render-test/videos/sample-product"
MP4 = os.path.join(ROOT, "renders", "video.mp4")
FRAME_DIR = os.path.join(ROOT, "renders", "_frames")
FFMPEG = "your Homebrew bin/ffmpeg"
FFPROBE = "your Homebrew bin/ffprobe"

# Timeline (seconds) — one per scene + both sides of every boundary + hook + CTA.
SAMPLES = [
    (1.5, "hook_a"), (2.5, "hook_b"),
    (5.75, "b1_end"), (6.25, "b1_crossfade"),
    (9.0, "scene2_mid"),
    (12.75, "b2_end"), (13.25, "b2_crossfade"),
    (17.0, "scene3_mid"),
    (22.75, "b3_end"), (23.25, "b3_crossfade"),
    (27.0, "scene4_mid"), (28.0, "cta_a"), (29.5, "cta_b"),
]

# Brand palette (cal.com cobalt system).
COLORS = {
    "cobalt_hairline": (0x00, 0x99, 0xFF),
    "cobalt_text":     (0x00, 0x77, 0xCC),
    "cobalt_soft":     (0x00, 0x5B, 0xB0),
    "paper_white":     (0xFF, 0xFF, 0xFF),
}
TOL = 14

def near(a, b, tol=TOL):
    return all(abs(x - y) <= tol for x, y in zip(a, b))

def ensure_frames():
    os.makedirs(FRAME_DIR, exist_ok=True)
    for t, name in SAMPLES:
        out = os.path.join(FRAME_DIR, f"{name}.png")
        if os.path.exists(out):
            continue
        cmd = [FFMPEG, "-y", "-ss", f"{t}", "-i", MP4,
               "-frames:v", "1", "-vf", "scale=1920:1080", out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  !! ffmpeg failed for t={t}: {r.stderr[-300:]}", file=sys.stderr)

def describe(path):
    with Image.open(path) as raw:
        im = raw.convert("RGB")
    w, h = im.size
    counts = Counter(im.getdata())
    total = w * h
    out = {"file": os.path.basename(path), "size": f"{w}x{h}"}
    out["dominant"] = [list(c) for c, _ in counts.most_common(4)]
    out["center"] = list(im.load()[w // 2, h // 2])
    nw = sum(n for c, n in counts.items() if not near(c, (255, 255, 255)))
    out["non_white_pct"] = round(100 * nw / total, 2)
    nb = sum(n for c, n in counts.items() if near(c, (0, 0, 0)))
    out["near_black_pct"] = round(100 * nb / total, 3)
    hits = {}
    for name, tgt in COLORS.items():
        hits[name] = sum(n for c, n in counts.items() if near(c, tgt))
    out["color_hits_pct"] = {k: round(100 * v / total, 3) for k, v in hits.items()}
    return im, out

def diff_pair(a, b):
    if a.size != b.size:
        return None
    da, db = a.getdata(), b.getdata()
    step = max(1, len(da) // 200_000)
    tot, n = 0, 0
    for i in range(0, len(da), step):
        pa, pb = da[i], db[i]
        tot += abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])
        n += 3
    return tot / n

def ffprobe():
    cmd = [FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", MP4]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"error": r.stderr[-300:]}
    d = json.loads(r.stdout)
    info = {"duration": float(d["format"].get("duration", 0)),
            "format": d["format"].get("format_name")}
    streams = []
    for s in d.get("streams", []):
        streams.append({"codec_type": s.get("codec_type"),
                        "codec": s.get("codec_name"),
                        "w": s.get("width"), "h": s.get("height"),
                        "duration": s.get("duration")})
    info["streams"] = streams
    return info

def audio_peak():
    """Mix down to mono wav and report peak sample (dim-5 P evidence)."""
    tmp = os.path.join(FRAME_DIR, "_mixed.wav")
    cmd = [FFMPEG, "-y", "-i", MP4, "-ac", "1", "-ar", "44100", tmp]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp):
        return {"error": "audio extract failed"}
    import struct
    with open(tmp, "rb") as f:
        f.read(44)
        data = f.read()
    vals = struct.unpack("<%dh" % (len(data) // 2), data)
    peak = max(abs(v) for v in vals) if vals else 0
    return {"peak_16bit": peak, "peak_pct": round(100 * peak / 32768, 1)}

def main():
    if not os.path.exists(MP4):
        print("NO MP4 at", MP4); sys.exit(2)
    ensure_frames()
    report = {"frames": [], "diffs": [], "media": None, "audio": None}
    imgs = []
    paths = [os.path.join(FRAME_DIR, f"{name}.png") for _, name in SAMPLES]
    for p in paths:
        im, desc = describe(p)
        imgs.append(im)
        report["frames"].append(desc)
    for i in range(len(imgs) - 1):
        d = diff_pair(imgs[i], imgs[i + 1])
        a, b = SAMPLES[i][1], SAMPLES[i + 1][1]
        verdict = "static" if (d is not None and d < 2) else (
                  "gradual" if (d is not None and d <= 25) else "HARD_CUT")
        report["diffs"].append({"from": a, "to": b, "mean_abs_diff": round(d, 2) if d else None,
                                "reading": verdict})
    report["media"] = ffprobe()
    report["audio"] = audio_peak()
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
