"""Grounding stage — runs against the emitted project, not the spec.

Grounding has to be checked *after* emission because a treatment can be
perfectly well-behaved in the spec and still emit copy that no claim licenses.
"""

from __future__ import annotations

from typing import Any

from ...content.grounding import check_scene_grounding
from ...spec.schema import VideoSpec
from ..runner import StageResult


def claim_grounding(
    spec: VideoSpec,
    *,
    scene_fragments: dict[str, str] | None = None,
    **_: Any,
) -> StageResult:
    if not scene_fragments:
        return StageResult(
            stage_id="claim_grounding",
            passed=False,
            problems=["no emitted fragments to check; run emit first"],
        )

    problems: list[str] = []
    per_scene: list[dict[str, str]] = []

    for scene in spec.scenes:
        fragment = scene_fragments.get(scene.scene_id)
        if fragment is None:
            problems.append(f"scene {scene.scene_id}: no emitted fragment")
            continue
        for issue in check_scene_grounding(spec, scene, fragment):
            problems.append(str(issue))
            per_scene.append(issue.to_dict())

    return StageResult(
        stage_id="claim_grounding",
        passed=not problems,
        problems=problems,
        detail={"per_scene": per_scene, "scenes_checked": len(spec.scenes)},
    )
