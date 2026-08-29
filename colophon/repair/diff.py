"""Spec diffing and locality proof.

Repair is only trustworthy if it is local. Change one scene's copy and only
that scene should re-render; if five scenes move, the edit was not local and a
"targeted" repair is really a full re-render wearing a costume.

``locality_report`` is the check that says which of those happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..spec.hash import diff_scene_hashes, scene_hashes
from ..spec.schema import Scene, VideoSpec


@dataclass
class SpecDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    field_changes: dict[str, list[str]] = field(default_factory=dict)

    @property
    def touched(self) -> list[str]:
        return sorted(set(self.added) | set(self.removed) | set(self.changed))

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": self.added,
            "removed": self.removed,
            "changed": self.changed,
            "unchanged": self.unchanged,
            "field_changes": self.field_changes,
        }


_SCENE_FIELDS = (
    "role",
    "treatment",
    "duration_s",
    "title_claim_id",
    "narration_claim_id",
    "asset_ids",
    "treatment_params",
    "renderer_hints",
)


def diff_specs(before: VideoSpec, after: VideoSpec) -> SpecDiff:
    """Scene-level diff between two specs."""
    before_map = {s.scene_id: s for s in before.scenes}
    after_map = {s.scene_id: s for s in after.scenes}

    hashes = diff_scene_hashes(scene_hashes(before), scene_hashes(after))
    diff = SpecDiff(
        added=hashes["added"],
        removed=hashes["removed"],
        changed=hashes["changed"],
        unchanged=hashes["unchanged"],
    )

    for scene_id in diff.changed:
        b, a = before_map.get(scene_id), after_map.get(scene_id)
        if b is None or a is None:
            continue
        fields = [f for f in _SCENE_FIELDS if getattr(b, f) != getattr(a, f)]
        if fields:
            diff.field_changes[scene_id] = fields

    return diff


def locality_report(
    before: VideoSpec, after: VideoSpec, intended: list[str]
) -> dict[str, Any]:
    """Did the edit stay where it was aimed?

    ``intended`` is the list of scene ids the author meant to change. Any
    other scene whose hash moved is collateral, and the report says so.
    """
    diff = diff_specs(before, after)
    intended_set = set(intended)
    collateral = sorted(set(diff.touched) - intended_set)
    missed = sorted(intended_set - set(diff.touched))

    return {
        "local": not collateral,
        "intended": sorted(intended_set),
        "touched": diff.touched,
        "collateral": collateral,
        "unchanged_after_edit": missed,
        "field_changes": diff.field_changes,
        "scene_hashes_before": scene_hashes(before),
        "scene_hashes_after": scene_hashes(after),
    }


def retime_required(before: VideoSpec, after: VideoSpec) -> bool:
    """Does this edit move the clock?

    Any duration change shifts every downstream scene, so the timeline — and
    therefore every scene after the edit — has to be rebuilt.
    """
    if len(before.scenes) != len(after.scenes):
        return True
    return any(
        b.duration_s != a.duration_s for b, a in zip(before.scenes, after.scenes)
    )
