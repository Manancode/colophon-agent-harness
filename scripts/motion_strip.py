#!/usr/bin/env python3
"""Build a motion time-strip: one row per motion, sampled at keyframe times.

The default contact sheet samples each scene at its midpoint, which is where
every entrance has already settled -- so all motions look identical and the
sheet cannot tell you whether a motion works at all. This samples at the
moments the motions actually move.

ffmpeg 8.1 from homebrew is built without libfreetype, so there is no
`drawtext` filter here. Labels and the montage are done with Pillow instead,
which also removes the ffmpeg 8.x single-input `tile` constraint.

Usage:
    python3 scripts/motion_strip.py                 # latest attempt
    python3 scripts/motion_strip.py --attempt 3
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

REPO = Path(__file__).resolve().parent.parent


def _ffmpeg() -> str:
    """Locate ffmpeg without hardcoding anyone's machine.

    ``$FFMPEG`` wins, then ``$PATH``. Homebrew's Cellar path is *not* on the
    default PATH on macOS, so it is probed last as a convenience — but only if
    it happens to exist here.
    """
    env = os.environ.get("FFMPEG")
    if env:
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if Path(candidate).exists():
            return candidate
    raise SystemExit(
        "ffmpeg not found. Install it, or set $FFMPEG to the binary path."
    )

#: Sampled relative to each scene's own start. Chosen to straddle the moments
#: the three motions differ: fade-rise 400ms, word-sweep stagger 0-660ms,
#: thinking-pulse cycle 1200ms (peaks at 35%/420ms and 65%/780ms).
OFFSETS = [0.05, 0.20, 0.35, 0.50, 0.80, 1.50]

SCENES = [
    ("fade-rise", 0.0),
    ("word-sweep", 2.5),
    ("thinking-pulse", 5.0),
]

TILE_W = 400
PAD = 12
BG = (11, 11, 13)

_FONT_CANDIDATES = (
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Monaco.ttf",
    "/System/Library/Fonts/Courier.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
)


def _font(size: int):
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def latest_attempt(run_dir: Path) -> int:
    attempts = sorted(
        (int(p.name) for p in (run_dir / "attempts").iterdir() if p.name.isdigit()),
        reverse=True,
    )
    if not attempts:
        raise SystemExit(f"no attempts under {run_dir / 'attempts'}")
    return attempts[0]


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(
            "command failed:\n  "
            + " ".join(str(c) for c in cmd)
            + "\n\n"
            + (proc.stderr or "").strip()[-2000:]
        )


def extract(video: Path, t: float, dest: Path) -> int:
    """One frame at time t; returns the PNG size in bytes.

    Single -ss before the input. The reusable extract_frames() seeks
    max(0, t-1) before the input and a further 1.0s after it, which lands at
    1.0s for every timestamp below 1.0s -- silently collapsing exactly the
    sub-second range these samples live in.
    """
    run([
        _ffmpeg(), "-y",
        "-ss", f"{t:.3f}",
        "-i", str(video),
        "-frames:v", "1",
        "-vf", f"scale={TILE_W}:-2",
        str(dest),
    ])
    return dest.stat().st_size


def label(img: Image.Image, text: str) -> Image.Image:
    """Burn a timecode into the bottom-left corner."""
    layer = img.convert("RGBA")
    draw = ImageDraw.Draw(layer)
    font = _font(20)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    w, h = right - left, bottom - top
    x, y = 14, img.height - h - 22
    draw.rectangle([x - 8, y - 8, x + w + 8, y + h + 8], fill=(0, 0, 0, 165))
    draw.text((x, y), text, font=font, fill=(245, 245, 247, 255))
    return layer.convert("RGB")


def drift(a: Image.Image, b: Image.Image) -> float:
    """Mean absolute pixel difference -- how far frame `a` is from `b`."""
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3.0


def montage(rows: list[list[Image.Image]], out: Path) -> None:
    cols = max(len(r) for r in rows)
    tw, th = rows[0][0].size
    width = cols * tw + (cols + 1) * PAD
    height = len(rows) * th + (len(rows) + 1) * PAD
    sheet = Image.new("RGB", (width, height), BG)
    for r, row in enumerate(rows):
        for c, img in enumerate(row):
            sheet.paste(img, (PAD + c * (tw + PAD), PAD + r * (th + PAD)))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build a time-strip proving each motion is animating."
    )
    ap.add_argument("--run", default="motion-strip-01", help="run directory name")
    ap.add_argument("--attempt", type=int, default=None)
    args = ap.parse_args()

    run_dir = REPO / "runs" / args.run
    attempt = args.attempt or latest_attempt(run_dir)
    adir = run_dir / "attempts" / f"{attempt:02d}"
    video = adir / "artifact" / "launch-video.mp4"
    if not video.is_file():
        raise SystemExit(f"no video at {video}")

    frames_dir = adir / "review" / "strip-frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    rows: list[list[Image.Image]] = []
    for name, start in SCENES:
        images: list[Image.Image] = []
        sizes: list[int] = []
        for col, off in enumerate(OFFSETS):
            dest = frames_dir / f"{name}-{col:02d}.png"
            sizes.append(extract(video, start + off, dest))
            images.append(Image.open(dest).convert("RGB"))

        # The last sample (+1.50s) is past every motion's extent, so it is the
        # settled state. Drift from it is a direct measure of "still moving".
        settled = images[-1]
        drifts = [drift(im, settled) for im in images]
        labelled = [
            label(im, f"{name}  +{off:.2f}s" if col == 0 else f"+{off:.2f}s")
            for col, (im, off) in enumerate(zip(images, OFFSETS))
        ]
        rows.append(labelled)

        print(f"{name}")
        print("  offset : " + "  ".join(f"{o:>6.2f}" for o in OFFSETS))
        print("  png B  : " + "  ".join(f"{s:>6,}" for s in sizes))
        print("  drift  : " + "  ".join(f"{d:>6.2f}" for d in drifts))
        print()

    out = adir / "review" / "motion-strip.png"
    montage(rows, out)
    print(f"strip : {out}")
    print(f"        {out.stat().st_size:,} B")
    print("drift = mean abs pixel diff vs the settled frame (+1.50s);")
    print("        a row that starts high and falls to ~0 is animating.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
