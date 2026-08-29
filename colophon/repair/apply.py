"""Applying a targeted repair to a spec.

V0 keeps this deliberately dumb: a repair is an explicit list of
``(scene_id, field, value)`` operations plus optional claim edits. No fuzzy
patching, no heuristics. A repair you cannot read is a repair you cannot trust.

Localized re-rendering is intentionally NOT implemented in V0. Re-rendering a
subset of scenes through HyperFrames would need the renderer to support
partial composition, and doing it half-way would produce a video whose
timeline disagrees with its own plan. V0 re-renders the whole project but
still proves locality via ``locality_report``, so when partial rendering does
arrive the guarantee is already being measured.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from ..spec.schema import Claim, Scene, SpecError, VideoSpec
from .diff import diff_specs, locality_report, retime_required


@dataclass
class RepairOp:
    scene_id: str
    field: str
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return {"scene_id": self.scene_id, "field": self.field, "value": self.value}


@dataclass
class RepairResult:
    spec: VideoSpec
    report: dict[str, Any]
    ops: list[RepairOp] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"report": self.report, "ops": [o.to_dict() for o in self.ops]}


_SCENE_MUTABLE = frozenset(
    {"role", "treatment", "duration_s", "title_claim_id", "narration_claim_id", "asset_ids"}
)


def apply_ops(
    spec: VideoSpec, ops: list[RepairOp], claim_edits: dict[str, str] | None = None
) -> RepairResult:
    """Apply repairs and return the new spec plus a locality report.

    Only a whitelist of scene fields may be edited. ``treatment_params`` and
    ``renderer_hints`` are excluded on purpose: changing them changes what the
    scene looks like without changing what it says, and that is a styling
    decision that should go back through the authoring step, not a repair.
    """
    before = spec

    claims = list(spec.claims)
    if claim_edits:
        by_id = {c.claim_id: c for c in claims}
        for cid, text in claim_edits.items():
            if cid not in by_id:
                raise SpecError(f"claim {cid!r} does not exist")
            by_id[cid] = replace(by_id[cid], text=text)
        claims = [by_id[c.claim_id] for c in claims]

    scenes: list[Scene] = []
    index = {s.scene_id: s for s in spec.scenes}
    for op in ops:
        scene = index.get(op.scene_id)
        if scene is None:
            raise SpecError(f"scene {op.scene_id!r} does not exist")
        if op.field not in _SCENE_MUTABLE:
            raise SpecError(
                f"field {op.field!r} is not repairable; "
                f"allowed: {sorted(_SCENE_MUTABLE)}"
            )
        index[op.scene_id] = replace(scene, **{op.field: op.value})

    scenes = [index[s.scene_id] for s in spec.scenes]
    after = replace(spec, claims=tuple(claims), scenes=tuple(scenes))

    report = locality_report(before, after, [o.scene_id for o in ops])
    report["retime_required"] = retime_required(before, after)
    report["diff"] = diff_specs(before, after).to_dict()

    return RepairResult(spec=after, report=report, ops=list(ops))
