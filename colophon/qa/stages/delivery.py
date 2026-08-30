"""Delivery contract stage (gate 13).

Checks the spec against the delivery contract before anything is rendered. This
is the cheapest gate we have and the one that catches the most expensive
mistakes: shipping the wrong shape is only discoverable after an encode.
"""

from __future__ import annotations

from typing import Any

from ...spec.delivery import (
    DEFAULT_CONTRACT,
    VideoDeliveryContract,
    check_delivery,
    delivery_summary,
)
from ...spec.schema import VideoSpec
from ..runner import StageResult


def delivery_contract(
    spec: VideoSpec,
    plan: Any | None = None,
    contract: VideoDeliveryContract | None = None,
    rendered_duration_s: float | None = None,
    **_: Any,
) -> StageResult:
    """Fail the run when the spec is not a deliverable video.

    Runs before render, so it can only check what the spec and the timeline
    plan already know. Two durations are in play and the difference between
    them matters:

    * the *authored* total — the sum of scene durations.
    * the *timeline* total — what the composition actually runs for, which is
      shorter whenever the timeline declares an overlap (N adjacent scenes
      share ``overlap_s`` at each boundary).

    The timeline total is the delivery baseline, because it is what ships. Using
    the authored sum instead would score the declared overlap as drift and fail
    every match-cut video on the first frame.

    ``rendered_duration_s`` is optional and means the *measured* length of an
    encoded artifact. Pass it only when one exists: comparing a real encode
    against the timeline total is the drift check that catches dropped or
    padded frames. Without it no drift is claimed.

    ``contract`` overrides the default. Short motion-test fixtures are not
    deliverables and are *supposed* to fail this gate, so a caller that wants to
    gate a fixture rather than a video passes a relaxed contract explicitly.
    """
    limits = contract or DEFAULT_CONTRACT
    timeline = getattr(plan, "total_duration_s", None) if plan is not None else None
    problems = check_delivery(
        spec,
        limits,
        timeline_duration_s=timeline,
        rendered_duration_s=rendered_duration_s,
    )

    detail: dict[str, Any] = dict(delivery_summary(spec, timeline))
    detail["contract"] = {
        "width": limits.width,
        "height": limits.height,
        "fps": limits.fps,
        "duration_range_s": [limits.min_duration_s, limits.max_duration_s],
        "scene_range": [limits.min_scenes, limits.max_scenes],
    }
    detail["baseline"] = "timeline" if timeline is not None else "authored"
    if rendered_duration_s is not None:
        detail["rendered_duration_s"] = round(float(rendered_duration_s), 3)

    return StageResult(
        stage_id="delivery_contract",
        passed=not problems,
        problems=problems,
        detail=detail,
    )
