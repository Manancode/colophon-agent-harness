#!/usr/bin/env python3
"""
Consecutive-frame CONTENT-RESTRICTED diff.

Why "content-restricted": a launch video is ~97% flat background. A plain
whole-frame mean-abs-diff is diluted to ~0.00 by all those identical white
pixels and will happily report "no motion" on a frame where a whole scene
disappeared. So we only average over pixels that are NON-BACKGROUND in at
least one of the two frames.

Usage:
    python3 content_diff.py <video.mp4> <start> <end>

Prints "  fA->fB:   X.XX" for each consecutive pair in [start, end].

Guide (from review/criteria.md):
    < 2    static
    2-25   gradual (crossfade / push)  <- what a dissolve should read as
    > 60   hard cut
"""
import subprocess
import sys

import numpy as np
from PIL import Image

# A pixel counts as "content" if it is meaningfully darker than the page
# background. 250 keeps antialiased text edges but ignores white.
BG_THRESHOLD = 250


def read_gray(path: str) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("L"), dtype=np.int16)


def find_ffmpeg() -> str:
    """ffmpeg is at your Homebrew bin on this machine, which is NOT on the PATH
    that the sandboxed shell starts with. Resolve it once instead of requiring
    every caller to remember to export PATH."""
    import shutil

    for candidate in ("ffmpeg", "your Homebrew bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        found = shutil.which(candidate)
        if found:
            return found
    raise SystemExit("ffmpeg not found; install it or fix find_ffmpeg()")


FFMPEG = find_ffmpeg()


def extract(video: str, frame: int, out: str) -> None:
    subprocess.run(
        [
            FFMPEG, "-v", "error", "-y",
            "-i", video,
            "-vf", f"select=eq(n\\,{frame})",
            "-vframes", "1",
            out,
        ],
        check=True,
    )


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    video, start, end = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])

    tmp_a, tmp_b = "/tmp/_cd_a.png", "/tmp/_cd_b.png"
    extract(video, start, tmp_a)
    prev = read_gray(tmp_a)

    worst = 0.0
    worst_pair = ""
    for f in range(start + 1, end + 1):
        extract(video, f, tmp_b)
        cur = read_gray(tmp_b)
        mask = (prev < BG_THRESHOLD) | (cur < BG_THRESHOLD)
        if mask.any():
            diff = float(np.abs(cur - prev)[mask].mean())
        else:
            diff = 0.0
        print(f"  f{f - 1}->f{f}:   {diff:.2f}")
        if diff > worst:
            worst, worst_pair = diff, f"f{f - 1}->f{f}"
        prev = cur

    print(f"\n  worst: {worst:.2f} at {worst_pair}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
