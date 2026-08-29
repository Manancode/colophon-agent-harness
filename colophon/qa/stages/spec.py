"""Stages that check the spec itself, before anything is rendered."""

from __future__ import annotations

from typing import Any

from ...presentation.roles import check_narrative_order
from ...spec.schema import VideoSpec
from ...spec.validate import validate
from ...timeline.plan import TimelinePlan, check_continuity
from ..runner import StageResult


def spec_validate(spec: VideoSpec, **_: Any) -> StageResult:
    problems = validate(spec)
    return StageResult(
        stage_id="spec_validate",
        passed=not problems,
        problems=problems,
        detail={"scene_count": len(spec.scenes), "claim_count": len(spec.claims)},
    )


def timeline_continuity(
    spec: VideoSpec, plan: TimelinePlan, **_: Any
) -> StageResult:
    max_overlap = int(round(spec.timeline.overlap_s * spec.canvas.fps))
    problems = check_continuity(plan, max_overlap)
    return StageResult(
        stage_id="timeline_continuity",
        passed=not problems,
        problems=problems,
        detail={
            "fps": plan.fps,
            "total_frames": plan.total_frames,
            "total_duration_s": plan.total_duration_s,
            "overlap_frames": max_overlap,
        },
    )


def narrative_order(spec: VideoSpec, **_: Any) -> StageResult:
    """Advisory: structurally odd running orders.

    Never blocks a delivery on its own — a launch may legitimately open on the
    problem — but it is recorded so a reviewer sees it was considered.
    """
    problems = check_narrative_order([s.role for s in spec.scenes])
    return StageResult(
        stage_id="narrative_order",
        passed=True,
        problems=problems,
        advisory=True,
        detail={"roles": [s.role for s in spec.scenes]},
    )
