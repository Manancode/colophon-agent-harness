"""Video delivery contract — the hard boundary a deliverable must satisfy.

The *shape* here is borrowed from a research harness we studied: one typed,
fail-closed object that declares what a finished video is, checked before render
rather than discovered afterwards. What we did **not** borrow is its numbers,
and that distinction is the whole point of this module.

The reference contract was written for five-to-ten minute narrated explainers:
300-600 seconds and 10-14 scenes. Colophon makes short launch videos. Every real
run in this repository is 7.5-45 seconds across 3-34 scenes, so porting those
bounds verbatim would reject 100% of our own corpus. The numbers below are
derived from our runs instead, widened for headroom.

The contract is a *default* a caller can tighten or loosen. A contract that
cannot be adjusted is a contract that gets deleted the first time it is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import VideoSpec

#: The canvas colophon delivers on; every renderer we target is pinned to it.
CANONICAL_WIDTH = 1920
CANONICAL_HEIGHT = 1080
CANONICAL_FPS = 30

#: Envelope of real runs in this repository (7.5s-45s, 3-34 scenes), widened
#: for headroom rather than copied from an unrelated product category.
DEFAULT_MIN_DURATION_S = 5.0
DEFAULT_MAX_DURATION_S = 180.0
DEFAULT_MIN_SCENES = 1
DEFAULT_MAX_SCENES = 48

#: Below this a scene cannot register as a scene — it is a flash, not a beat.
DEFAULT_MIN_SCENE_DURATION_S = 0.5

#: Slack allowed between authored total and rendered total.
DEFAULT_DURATION_TOLERANCE_S = 0.5


@dataclass(frozen=True)
class VideoDeliveryContract:
    """What counts as a deliverable video.

    Checked before render. Each field is a bound, not a preference: a spec
    outside these bounds is not something we can ship, and saying so early is
    far cheaper than discovering it after the encoder has run.
    """

    width: int = CANONICAL_WIDTH
    height: int = CANONICAL_HEIGHT
    fps: int = CANONICAL_FPS
    min_duration_s: float = DEFAULT_MIN_DURATION_S
    max_duration_s: float = DEFAULT_MAX_DURATION_S
    min_scenes: int = DEFAULT_MIN_SCENES
    max_scenes: int = DEFAULT_MAX_SCENES
    min_scene_duration_s: float = DEFAULT_MIN_SCENE_DURATION_S
    duration_tolerance_s: float = DEFAULT_DURATION_TOLERANCE_S


DEFAULT_CONTRACT = VideoDeliveryContract()


def authored_duration_s(spec: VideoSpec) -> float:
    """Total seconds the spec's scenes claim, ignoring timeline overlap.

    This is *not* the length of the delivered video whenever the timeline
    declares a non-zero overlap: with the ``adjacent`` policy, consecutive
    scenes share ``overlap_s``, so N scenes sum to more than the composition
    runs. Use the laid-out timeline total as the delivery baseline whenever
    one is available.
    """
    return sum(float(scene.duration_s) for scene in spec.scenes)


def baseline_duration_s(
    spec: VideoSpec,
    timeline_duration_s: float | None = None,
) -> float:
    """The number every duration bound is measured against.

    Prefers ``timeline_duration_s`` (what will actually be rendered) and falls
    back to the naive sum of scene durations (all a caller with only a spec can
    know). The two agree exactly when the timeline overlap is zero.
    """
    if timeline_duration_s is None:
        return authored_duration_s(spec)
    return float(timeline_duration_s)


def check_delivery(
    spec: VideoSpec,
    contract: VideoDeliveryContract | None = None,
    *,
    timeline_duration_s: float | None = None,
    rendered_duration_s: float | None = None,
) -> list[str]:
    """Return every way ``spec`` misses the contract.

    An empty list means it ships. Every violation is reported rather than the
    first one raising, because seeing the full set at once is what makes a
    contract cheap to fix against.

    ``timeline_duration_s`` is the laid-out length of the composition. Pass it
    whenever a timeline plan exists: it, not the sum of scene durations, is
    what ships. Comparing the two would report the declared overlap as drift,
    so every spec using a match-cut transition would fail by construction.

    ``rendered_duration_s`` is the *measured* length of an encoded artifact.
    Comparing that against the baseline is the only real drift check — it is
    what catches an encoder that drops or pads frames.
    """
    limits = contract or DEFAULT_CONTRACT
    problems: list[str] = []
    total = baseline_duration_s(spec, timeline_duration_s)
    baseline = "timeline" if timeline_duration_s is not None else "authored"

    canvas = spec.canvas
    if canvas.width != limits.width or canvas.height != limits.height:
        problems.append(
            f"canvas {canvas.width}x{canvas.height} is not the contracted "
            f"{limits.width}x{limits.height}"
        )
    if canvas.fps != limits.fps:
        problems.append(f"canvas fps {canvas.fps} is not the contracted {limits.fps}")

    scenes = tuple(spec.scenes)
    count = len(scenes)
    if not limits.min_scenes <= count <= limits.max_scenes:
        problems.append(
            f"scene count {count} is outside "
            f"[{limits.min_scenes}, {limits.max_scenes}]"
        )

    if not limits.min_duration_s <= total <= limits.max_duration_s:
        problems.append(
            f"{baseline} duration {total:.2f}s is outside "
            f"[{limits.min_duration_s:.2f}, {limits.max_duration_s:.2f}]"
        )

    for scene in scenes:
        duration = float(scene.duration_s)
        if duration < limits.min_scene_duration_s:
            problems.append(
                f"scene {scene.scene_id} lasts {duration:.2f}s, under the "
                f"{limits.min_scene_duration_s:.2f}s minimum"
            )

    seen: set[str] = set()
    for scene in scenes:
        if scene.scene_id in seen:
            problems.append(f"duplicate scene_id {scene.scene_id!r}")
        seen.add(scene.scene_id)

    if rendered_duration_s is not None:
        drift = abs(float(rendered_duration_s) - total)
        if drift > limits.duration_tolerance_s:
            problems.append(
                f"rendered duration {rendered_duration_s:.2f}s drifts "
                f"{drift:.2f}s from the {baseline} total {total:.2f}s, over "
                f"the {limits.duration_tolerance_s:.2f}s tolerance"
            )

    return problems


def delivery_summary(
    spec: VideoSpec,
    timeline_duration_s: float | None = None,
) -> dict[str, object]:
    """A compact, loggable account of where a spec sits against the default."""
    summary: dict[str, object] = {
        "canvas": [spec.canvas.width, spec.canvas.height, spec.canvas.fps],
        "scene_count": len(spec.scenes),
        "authored_duration_s": round(authored_duration_s(spec), 3),
        "min_scene_duration_s": (
            round(min(float(s.duration_s) for s in spec.scenes), 3)
            if spec.scenes
            else 0.0
        ),
    }
    if timeline_duration_s is not None:
        summary["timeline_duration_s"] = round(float(timeline_duration_s), 3)
        summary["overlap_s"] = round(
            authored_duration_s(spec) - float(timeline_duration_s), 3
        )
    return summary
