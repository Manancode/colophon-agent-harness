#!/usr/bin/env python3
"""
OCR tool for the review gate — read the text that actually rendered.

Why this exists: the pixel sampler (sample_frames.py) proves what COLORS
rendered; it cannot tell you what the frame SAYS. Dimensions 1 (hook),
2 (capability accuracy), 3 (brand text) and 7 (CTA) all hinge on the actual
on-screen words. Guessing them from the source is inference; OCR is evidence.

Uses the macOS Vision framework (no external binary needed).

Setup (one time):
  <agent-runtime>/binaries/python/versions/3.13.12/bin/python3 \
      -m venv <agent-runtime>/binaries/python/envs/default
  <agent-runtime>/binaries/python/envs/default/bin/pip install \
      pyobjc-framework-Vision pyobjc-framework-Quartz

Usage:
  python3 ocr_frames.py frame1.png frame2.png ...
  python3 ocr_frames.py out/*.png --grep a third-party site      # flag matches only
  python3 ocr_frames.py out/*.png --grep a third-party site,another app --show-all

Exit code 1 if any --grep term is found (handy as a CI-style gate).
"""

import argparse
import sys

try:
    import Vision
    import Quartz
    from Foundation import NSURL
except ImportError:
    sys.exit(
        "pyobjc Vision bindings missing. Install with:\n"
        "  <venv>/bin/pip install pyobjc-framework-Vision pyobjc-framework-Quartz"
    )


def ocr_image(path: str):
    url = NSURL.fileURLWithPath_(path)
    ci_image = Quartz.CIImage.imageWithContentsOfURL_(url)
    if ci_image is None:
        raise RuntimeError(f"could not load image: {path}")

    handler = Vision.VNImageRequestHandler.alloc().initWithCIImage_options_(ci_image, None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    request.setRecognitionLanguages_(["en-US"])

    ok, err = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(f"Vision request failed for {path}: {err}")

    lines = []
    for observation in (request.results() or []):
        candidates = observation.topCandidates_(1)
        if candidates and len(candidates):
            lines.append(candidates[0].string())
    return lines


def main():
    ap = argparse.ArgumentParser(description="OCR rendered frames with macOS Vision.")
    ap.add_argument("frames", nargs="+")
    ap.add_argument("--grep", default="",
                    help="comma-separated terms to flag (case-insensitive)")
    ap.add_argument("--show-all", action="store_true",
                    help="print full OCR text even when --grep is used")
    args = ap.parse_args()

    terms = [t.strip().lower() for t in args.grep.split(",") if t.strip()]
    hits = []

    for path in args.frames:
        try:
            lines = ocr_image(path)
        except Exception as exc:                       # noqa: BLE001
            print(f"== {path}  ERROR: {exc}", file=sys.stderr)
            continue

        joined = "\n".join(lines)
        lower = joined.lower()
        found = [t for t in terms if t in lower]

        print(f"== {path}  ({len(lines)} text blocks)")
        if found:
            hits.append((path, found))
            print(f"   !! MATCH: {', '.join(found)}")
        if args.show_all or not terms:
            for line in lines:
                print(f"   | {line}")
        elif found:
            # still show context so a human can confirm it is a real hit
            for line in lines:
                if any(t in line.lower() for t in found):
                    print(f"   | {line}")

    if terms:
        print(f"\n-- grep summary: {len(hits)} frame(s) matched --")
        for path, found in hits:
            print(f"   {path}: {', '.join(found)}")
        if hits:
            sys.exit(1)


if __name__ == "__main__":
    main()
