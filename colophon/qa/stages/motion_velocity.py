"""Pixel-velocity floor for emitted motion (gate 12).

colophon emits its motion as CSS keyframes that play in real browsers. When a
transform's total travel is small relative to its duration, each rendered frame
moves well under one pixel, so the eye sees a *stutter* (sits still, then jumps)
rather than a glide -- it reads as a defect, not a motion.

So we measure the *artifact*, not the generator's intent (the project's standing
rule: validate the output, don't trust the emitter). For every @keyframes that
moves via translateY we pair its travel distance with the animation-duration it
actually runs at, divide by the render fps, and flag anything under the floor.
We also check the word-sweep stagger stays >= 2 frames so consecutive words read
as a cascade, not a single jumble.

This is fps-aware on purpose: render at 60fps and a motion that was fine at 30fps
will be flagged, which is the correct signal that the timing needs retuning.
"""

from __future__ import annotations

import re
from typing import Any

from ...spec.schema import VideoSpec
from ..css import keyframes_blocks
from ..runner import StageResult

#: Per-frame pixel-velocity floor, in pixels per frame.
FLOOR_PX_PER_FRAME = 1.0
#: Minimum word-sweep stagger, in frames, so words don't blur together.
MIN_STAGGER_FRAMES = 2

_TRANSLATEY_RE = re.compile(r"translateY\(([-0-9.]+)px\)")
_WORD_SPAN_RE = re.compile(r'class="word"[^>]*?animation-(?:delay|duration)\s*:\s*(\d+)ms')
_WORD_DELAY_RE = re.compile(r'class="word"[^>]*?animation-delay\s*:\s*(\d+)ms')
_WORD_SWEEP_H1_RE = re.compile(
    r'<h1[^>]*data-motion="word-sweep"[^>]*>(.*?)</h1>', re.S
)


def _resolve_fps(spec: VideoSpec) -> int:
    timeline = getattr(spec, "timeline", None)
    fps = getattr(timeline, "fps", None) if timeline is not None else None
    if fps is None:
        fps = getattr(spec, "fps", None)
    return int(fps) if fps else 30


def _duration_for_keyframe(document: str, name: str) -> int | None:
    """Resolve the duration (ms) a keyframe actually runs for, in ms.

    Tries a CSS rule that names the keyframe and also sets a duration, then
    falls back to colophon's known emission: word-sweep durations live on the
    .word spans, fade-rise durations on the .clip-motion scene wrapper.
    """
    for body in (m.group(2) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", document)):
        if re.search(r"animation-name\s*:\s*" + re.escape(name) + r"\b", body):
            dm = re.search(r"animation-duration\s*:\s*(\d+)ms", body)
            if dm:
                return int(dm.group(1))
    if name == "word-sweep-in":
        vals = re.findall(
            r'class="word"[^>]*?animation-duration\s*:\s*(\d+)ms', document
        )
        if vals:
            return int(vals[0])
    if name == "colophon-in":
        dm = re.search(
            r'"scene-body clip-motion"[^>]*?animation-duration\s*:\s*(\d+)ms', document
        )
        if dm:
            return int(dm.group(1))
    return None


def motion_pixel_velocity(
    spec: VideoSpec, *, document: str | None = None, **_: Any
) -> StageResult:
    fps = _resolve_fps(spec)
    if not document:
        return StageResult(
            "motion_pixel_velocity",
            passed=True,
            advisory=True,
            problems=["no rendered document to measure pixel velocity"],
        )

    problems: list[str] = []
    detail: dict[str, Any] = {}

    for block in keyframes_blocks(document):
        name = block.name
        # Travel is summed across every step, not read off the first one. The
        # regex this used (`@keyframes name {(.*?)}`) stopped at the close of
        # the first step, so a motion whose travel sits in a later step
        # measured 0px and was reported as a stutter no matter how far it
        # actually moved. colophon's own emitter happens to put the travel in
        # the `from` step, which is the only reason this ever looked correct.
        dists = [
            abs(float(x))
            for _, decls in block.steps
            for x in _TRANSLATEY_RE.findall(decls)
        ]
        if not dists:
            continue
        max_dist = max(dists)
        dur = _duration_for_keyframe(document, name)
        if dur is None:
            continue
        frames = (dur / 1000.0) * fps
        px_per_frame = max_dist / frames if frames > 0 else float("inf")
        if px_per_frame < FLOOR_PX_PER_FRAME:
            problems.append(
                f"{name}: moves {max_dist:g}px over {dur}ms @ {fps}fps "
                f"= {px_per_frame:.2f}px/frame (< {FLOOR_PX_PER_FRAME:g} floor; stutters)"
            )
            detail[name] = {
                "px": max_dist,
                "ms": dur,
                "fps": fps,
                "px_per_frame": round(px_per_frame, 3),
            }

    for h1 in _WORD_SWEEP_H1_RE.finditer(document):
        block = h1.group(1)
        delays = [int(x) for x in _WORD_DELAY_RE.findall(block)]
        if len(delays) < 2:
            continue
        step = min(delays[i + 1] - delays[i] for i in range(len(delays) - 1))
        step_frames = step / 1000.0 * fps
        if step_frames < MIN_STAGGER_FRAMES:
            problems.append(
                f"word-sweep stagger {step}ms = {step_frames:.2f}f "
                f"< {MIN_STAGGER_FRAMES}f minimum (words blur together)"
            )
            detail.setdefault("stagger_ms", step)

    return StageResult(
        "motion_pixel_velocity",
        passed=not problems,
        problems=problems,
        detail=detail,
    )
