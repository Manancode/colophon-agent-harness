#!/usr/bin/env python3
"""
Pixel-sampling tool for the review gate's "P channel" (evidence you can count).

Why this exists: most agents running this harness cannot actually see a PNG.
Scoring `brand_consistency_and_visual_craft: 5` because "the frame looks clean"
is fabrication. This script turns visual claims into numbers.

Usage
-----
  python3 sample_frames.py frame1.png frame2.png ...

  # with brand colors to check (repeatable, NAME=HEX)
  python3 sample_frames.py out/*.png \
      --color accent=#0ea5e9 --color offbrand=#8b5cf6

  # also report frame-to-frame difference (hard-cut detection, dimension 4)
  python3 sample_frames.py out/review-f*.png --diff

Interpreting --diff (dimension 4, motion_continuity_and_pacing)
--------------------------------------------------------------
  mean abs diff < 2    -> essentially identical frames (dead hold)
  2 .. 25              -> gradual change (crossfade / push / animate)  GOOD
  > 60                 -> near-total change in one step = HARD CUT

Notes
-----
- Requires Pillow. Verified working with PIL 12.3.0 on Python 3.13.
- Frames are compared in the order given on the command line, so pass them
  in timeline order.
"""

import argparse
import sys

try:
    from PIL import Image
    from collections import Counter
except ImportError:
    sys.exit("Pillow is required: pip install pillow")


def parse_hex(value: str):
    value = value.strip().lstrip("#")
    if len(value) == 8:          # RGBA -> drop alpha
        value = value[:6]
    if len(value) != 6:
        raise argparse.ArgumentTypeError(f"bad hex color: {value!r}")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def near(a, b, tol=12):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def describe(path, colors, tol, top_n):
    with Image.open(path) as raw:
        im = raw.convert("RGB")
    w, h = im.size
    counts = Counter(im.getdata())
    total = w * h

    print(f"== {path}  ({w}x{h}, {total:,} px)")

    for col, n in counts.most_common(top_n):
        print(f"   dominant  rgb{col}  {n:>10,}  {100*n/total:6.2f}%")

    print(f"   center    rgb{im.load()[w//2, h//2]}")

    nonwhite = sum(n for col, n in counts.items() if not near(col, (255, 255, 255), tol))
    print(f"   non-white {nonwhite:>10,}  {100*nonwhite/total:6.2f}%")

    near_black = sum(n for col, n in counts.items() if near(col, (0, 0, 0), tol))
    print(f"   near-black{near_black:>10,}  {100*near_black/total:6.2f}%")

    for name, target in colors.items():
        hit = sum(n for col, n in counts.items() if near(col, target, tol))
        print(f"   {name:<11} rgb{target} {hit:>10,}  {100*hit/total:6.2f}%")

    return im


def diff_pair(a, b):
    """Mean absolute per-channel difference between two same-size RGB images."""
    if a.size != b.size:
        return None
    da, db = a.getdata(), b.getdata()
    step = max(1, len(da) // 200_000)          # sample for speed on large frames
    total, n = 0, 0
    for i in range(0, len(da), step):
        pa, pb = da[i], db[i]
        total += abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])
        n += 3
    return total / n


def main():
    ap = argparse.ArgumentParser(
        description="Sample rendered frames into numbers for the review gate.")
    ap.add_argument("frames", nargs="+", help="PNG files, in timeline order")
    ap.add_argument("--color", action="append", default=[], metavar="NAME=HEX",
                    help="brand color to count, e.g. accent=#0ea5e9 (repeatable)")
    ap.add_argument("--tol", type=int, default=12, help="color tolerance (default 12)")
    ap.add_argument("--top", type=int, default=5, help="dominant colors to print (default 5)")
    ap.add_argument("--diff", action="store_true",
                    help="also report frame-to-frame difference (hard-cut detection)")
    args = ap.parse_args()

    colors = {}
    for spec in args.color:
        if "=" not in spec:
            ap.error(f"--color expects NAME=HEX, got {spec!r}")
        name, hexval = spec.split("=", 1)
        colors[name] = parse_hex(hexval)

    images = []
    for path in args.frames:
        try:
            images.append(describe(path, colors, args.tol, args.top))
        except FileNotFoundError:
            print(f"== {path}  MISSING", file=sys.stderr)
        except Exception as exc:                        # noqa: BLE001
            print(f"== {path}  ERROR: {exc}", file=sys.stderr)

    if args.diff and len(images) > 1:
        print("\n-- frame-to-frame mean abs diff (dimension 4) --")
        for i in range(len(images) - 1):
            d = diff_pair(images[i], images[i + 1])
            if d is None:
                print(f"   {args.frames[i]} -> {args.frames[i+1]}: size mismatch")
                continue
            if d < 2:
                verdict = "static hold"
            elif d <= 25:
                verdict = "gradual (crossfade/push)"
            else:
                verdict = "HARD CUT"
            print(f"   {args.frames[i]} -> {args.frames[i+1]}: {d:6.2f}  {verdict}")


if __name__ == "__main__":
    main()
