"""Structural checks on what the composition actually draws (gate 14).

Every other gate asks whether something is *true*: is the copy grounded, is
the accent right, is the motion fast enough to read. This one asks a prior
question — is there anything there at all?

The six ways a scene can be scheduled on the clock and still draw nothing:
it can be scheduled for zero frames, it can have no content, it can animate
an element the renderer never emitted, it can animate its content to
invisible and leave it there, it can reference an asset that isn't on disk,
or it can simply encode to a blank frame.

These are the cheap, stupid failures, and they are worth a dedicated gate for
two reasons. First, they are invisible to gates that inspect *properties* of
content: a scene with no content has perfectly consistent colours and no
unsupported claims. Second, they are the failures a human reviewer notices
in the first second and a determinism-obsessed pipeline notices never,
because nothing about them is non-deterministic.

All of these check the artifact rather than the spec. The spec can promise a
title; only the emitted document can tell you whether a word span exists for
the motion to sweep.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from ..css import keyframes_blocks
from ..pipeline import NEEDS_PROJECT, gate_needs
from ..runner import StageResult

#: What each motion animates. A motion whose target is absent is not a
#: smaller motion -- it is no motion, rendered and shipped as if it ran.
#: This is the stat-hero bug class: the treatment built its own <h1> and never
#: emitted the word spans, so word-sweep was accepted, rendered, and did
#: nothing. The grammar now rejects that pair at spec time; this checks the
#: artifact, which is the only place a future emitter change can be caught.
MOTION_TARGETS: dict[str, tuple[str, str]] = {
    "word-sweep": (r'class="word"', "no word span"),
    "thinking-pulse": (r"data-centerpiece", "no centerpiece element"),
}

#: The baseline motion animates the .clip-motion wrapper, which every scene
#: has by construction, so it needs no target rule.
BASELINE_MOTION = "fade-rise"

_SCENE_MOTION_RE = re.compile(r'class="clip[^"]*?\bm-([\w-]+)\b')
_FRAGMENT_MOTION_RE = re.compile(r'data-motion="([\w-]+)"')
_ZERO_DURATION_RE = re.compile(r"animation-duration\s*:\s*0(?:ms|s)?\b")
_OPACITY_ZERO_RE = re.compile(r"opacity\s*:\s*0(?:\.0+)?\s*(?:!important)?\s*;?\s*$")
_SRC_RE = re.compile(r'(?:src|href)\s*=\s*"([^"]+)"')
_CSS_URL_RE = re.compile(r"url\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)")
_TAG_RE = re.compile(r"<[^>]+>")
_HEX_RE = re.compile(r"background\s*:\s*(#[0-9A-Fa-f]{3,8})")

#: How far a frame's brightest pixel must sit above its darkest before we
#: call it drawn. A frame showing only a flat background is perfectly flat,
#: so its spread is 0; a headline lifts it to ~215. Measured on a real run,
#: content lands at 214-217 and a solid-colour encode lands at exactly 0 at
#: every crf from 14 to 28, so this sits ~27x below content and ~8x above the
#: noise floor. High enough to absorb a little encoding texture, low enough
#: that nothing short of actual content clears it.
BLANK_SPREAD = 8.0


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _strip_tags(html: str) -> str:
    """Visible text in a fragment, with tags and entities removed."""
    text = _TAG_RE.sub(" ", html)
    text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)
    return " ".join(text.split())


def _srgb_luma(hex_color: str) -> float | None:
    """Luma of an sRGB hex colour on ffmpeg's ``signalstats`` scale (16-235).

    Not the 0-255 relative luminance, even though that is what the name
    suggests and what this used to return. Our encodes are yuv420p with
    ``color_range=tv``, so 0-255 sRGB is rescaled to 16-235 before it ever
    reaches the measurement: a #0B0B12 canvas reads 26, not 11.5, and white
    reads 235, not 255. Verified against solid-colour encodes across the
    range. Comparing a 0-255 formula against a 16-235 reading is a scale
    error, not a rounding error, and it made the blank check compare a
    measured frame against a floor ~14 units below where it belonged.
    """
    value = hex_color.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) not in (6, 8):
        return None
    try:
        r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None
    luma_0_255 = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return 16.0 + luma_0_255 * 219.0 / 255.0


def _local_assets(document: str) -> Iterable[str]:
    """Local paths referenced by the document (data: and remote are skipped)."""
    for match in list(_SRC_RE.finditer(document)) + list(_CSS_URL_RE.finditer(document)):
        ref = match.group(1).strip()
        if not ref or ref.startswith(("#", "data:", "http://", "https://", "//")):
            continue
        yield ref.split("?")[0].split("#")[0]


def _scene_background(fragment: str) -> float | None:
    """Luma of the scene's own background, read off the emitted style."""
    match = _HEX_RE.search(fragment)
    return _srgb_luma(match.group(1)) if match else None


# --------------------------------------------------------------------------
# The stage
# --------------------------------------------------------------------------


@gate_needs(NEEDS_PROJECT)
def scene_structure(
    spec: Any = None,
    plan: Any | None = None,
    document: str | None = None,
    scene_fragments: dict[str, str] | None = None,
    video_path: Any | None = None,
    project_dir: Any | None = None,
    **_: Any,
) -> StageResult:
    """Flag anything scheduled on the clock that draws nothing.

    ``video_path`` and ``project_dir`` are optional: the blank-frame and
    missing-asset checks are the only ones that need the filesystem, and the
    gate still catches the rest when it runs before a render.
    """
    problems: list[str] = []
    codes: list[str | None] = []
    detail: dict[str, Any] = {}

    def report(code: str, message: str) -> None:
        problems.append(message)
        codes.append(code)

    fragments = dict(scene_fragments or {})

    # -- zero duration ----------------------------------------------------
    # A scene scheduled for zero frames is not a short beat; it is a scene
    # that never appears, and every downstream gate will happily validate a
    # fragment no viewer will ever see.
    for window in getattr(plan, "windows", ()) or ():
        if getattr(window, "duration_frames", 1) <= 0:
            report(
                "structure.zero_duration",
                f"scene {window.scene_id} is scheduled for "
                f"{window.duration_frames} frames; it never appears",
            )
    if document and _ZERO_DURATION_RE.search(document):
        report(
            "structure.zero_duration",
            "a motion is set to animation-duration:0; it is scheduled but never plays",
        )

    # -- no visuals -------------------------------------------------------
    for scene_id, fragment in fragments.items():
        text = _strip_tags(fragment)
        has_media = bool(re.search(r"<(img|video|svg|canvas)\b", fragment, re.I))
        if not text and not has_media:
            report(
                "structure.no_visuals",
                f"scene {scene_id} has no text and no media; it renders blank",
            )

    # -- never visible ----------------------------------------------------
    # A motion class is on the scene, but the element it animates is not.
    for scene_id, fragment in fragments.items():
        motion_match = _SCENE_MOTION_RE.search(fragment) or _FRAGMENT_MOTION_RE.search(
            fragment
        )
        if not motion_match:
            continue
        motion = motion_match.group(1)
        if motion == BASELINE_MOTION:
            continue
        rule = MOTION_TARGETS.get(motion)
        if rule is None:
            # Unknown motion: we cannot say what it targets, so we cannot say
            # it worked. Say so rather than assuming.
            report(
                "structure.never_visible",
                f"scene {scene_id} carries motion {motion!r}, which has no "
                f"declared target; cannot confirm it animates anything",
            )
            continue
        pattern, why = rule
        if not re.search(pattern, fragment):
            report(
                "structure.never_visible",
                f"scene {scene_id} carries motion {motion!r} but {why} for it "
                f"to animate; the motion is a no-op",
            )

    # -- transparent ------------------------------------------------------
    # An entrance that ends fully transparent leaves the content invisible for
    # the rest of the scene, so the scene is present on the clock and blank on
    # screen. Nothing else in the pipeline can see this: the DOM is correct,
    # the colours are consistent, and the claims are all grounded.
    if document:
        for block in keyframes_blocks(document):
            final = block.final_step
            if final is None:
                continue
            if _OPACITY_ZERO_RE.search(final[1].strip()):
                report(
                    "structure.transparent",
                    f"keyframes {block.name} ends at opacity 0; content animated "
                    f"by it stays invisible for the rest of the scene",
                )

    # -- source error -----------------------------------------------------
    if document and project_dir is not None:
        root = Path(project_dir)
        for ref in sorted(set(_local_assets(document))):
            if not (root / ref).exists():
                report(
                    "structure.source_error",
                    f"document references {ref!r}, which does not exist under "
                    f"{root}",
                )

    # -- black frames -----------------------------------------------------
    # Measured, not inferred: read the actual encoded luma at each scene's
    # midpoint and ask whether the frame departs from a flat field at all.
    if video_path and plan is not None:
        measured = _blank_scenes(video_path, plan, fragments)
        if measured is not None:
            detail["luma"] = [
                {
                    "scene": scene_id,
                    "ymin": stats.ymin,
                    "yavg": stats.yavg,
                    "ymax": stats.ymax,
                    "spread": stats.spread,
                }
                for scene_id, stats, _ in measured
            ]
            for scene_id, stats, background in measured:
                spread = stats.spread
                if spread is None or spread > BLANK_SPREAD:
                    continue
                # Saying *which* flat colour it landed on is the difference
                # between "it drew its background and nothing else" and "it
                # drew something uniformly wrong".
                suffix = ""
                if background is not None and stats.yavg is not None:
                    if abs(stats.yavg - background) <= 2.0:
                        suffix = f", which is its declared background {background:.0f}"
                report(
                    "structure.black_frame",
                    f"scene {scene_id} draws nothing at its midpoint: "
                    f"YMIN {stats.ymin:.0f}..YMAX {stats.ymax:.0f} "
                    f"(spread {spread:.0f}){suffix}; the frame is blank",
                )

    detail["scene_count"] = len(fragments)
    detail["checks"] = sorted(
        {
            c.split(".")[1]
            for c in codes
            if c
        }
    )

    return StageResult(
        stage_id="scene_structure",
        passed=not problems,
        problems=problems,
        codes=codes,
        detail=detail,
    )


def _blank_scenes(
    video_path: Any, plan: Any, fragments: dict[str, str]
) -> list[tuple[str, Any, float | None]] | None:
    """Per-scene (id, measured luma stats, declared background luma).

    Returns None when the video cannot be measured, which is not the same as
    measuring it and finding nothing.
    """
    try:
        from ...review import extract as review_extract
    except Exception:  # noqa: BLE001 - review tooling is optional
        return None

    stamps = review_extract.scene_midpoints(plan)
    if not stamps:
        return None
    try:
        readings = review_extract.luma_stats_at(str(video_path), stamps)
    except Exception:  # noqa: BLE001 - a missing tool must not fail the gate
        return None

    windows = list(getattr(plan, "windows", ()) or ())
    out: list[tuple[str, Any, float | None]] = []
    for window, stats in zip(windows, readings):
        background = _scene_background(fragments.get(window.scene_id, ""))
        out.append((window.scene_id, stats, background))
    return out
