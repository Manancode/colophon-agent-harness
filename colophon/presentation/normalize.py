"""Explicit spec normalisation.

The one hard-won rule in this file: **never silently substitute**.

An earlier iteration rebuilt each scene from a fixed key set and dropped
everything else. When we added ``treatment``, it disappeared without an
error, and the video rendered as if the field had never existed. That is
the most expensive class of bug in this system, because the output looks
fine — it is just not the thing you asked for.

So this module either resolves a treatment explicitly or raises. The only
implicit behaviour is filling in a role's documented baseline when the field
is genuinely absent, and that is recorded in the returned log.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from ..content.claims import numbers_in
from ..spec.schema import Scene, SpecError, VideoSpec
from .treatments import (
    TREATMENTS,
    baseline_for_role,
    build_context,
    treatments_for_role,
    validate_treatment,
)

_TREATMENT_ID_RE = re.compile(r"[a-z][a-z0-9-]{1,63}")


class NormalizeLog:
    """What normalisation decided, so a run can explain itself afterwards."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def add(self, scene_id: str, action: str, detail: str) -> None:
        self.entries.append({"scene_id": scene_id, "action": action, "detail": detail})

    def to_dict(self) -> dict[str, Any]:
        return {"entries": list(self.entries)}

    def __bool__(self) -> bool:
        return bool(self.entries)


def resolve_treatment(spec: VideoSpec, scene: Scene, log: NormalizeLog) -> str:
    """Return the treatment a scene will use, or raise.

    Order of decisions:
      1. role has no treatments at all      -> error if a treatment was claimed
      2. treatment absent / blank           -> role baseline (logged)
      3. treatment malformed                -> error
      4. treatment unknown                  -> error
      5. treatment belongs to another role  -> error
      6. precondition fails                 -> error
    """
    available = treatments_for_role(scene.role)
    if not available:
        if scene.treatment and scene.treatment.strip():
            raise SpecError(
                f"{scene.scene_id}: claims treatment {scene.treatment!r} but the "
                f"grammar defines no treatments for role {scene.role!r}"
            )
        return ""

    raw = scene.treatment or ""
    if not raw.strip():
        baseline = baseline_for_role(scene.role)
        if baseline is None:
            raise SpecError(
                f"{scene.scene_id}: role {scene.role!r} has no baseline treatment "
                f"and no treatment was given"
            )
        log.add(scene.scene_id, "default_treatment", f"no treatment given; using baseline {baseline!r}")
        return baseline

    treatment = raw.strip()
    if not _TREATMENT_ID_RE.fullmatch(treatment):
        raise SpecError(
            f"{scene.scene_id}.treatment {treatment!r} is malformed; "
            f"expected lower kebab-case, e.g. 'hero-split'"
        )
    if treatment not in TREATMENTS:
        raise SpecError(
            f"{scene.scene_id}.treatment {treatment!r} is not in the grammar; "
            f"known treatments: {sorted(TREATMENTS)}"
        )

    title = spec.claim(scene.title_claim_id)
    narration = spec.claim(scene.narration_claim_id)
    ctx = build_context(
        scene=scene,
        title=title.text if title else "",
        narration=narration.text if narration else "",
    )
    try:
        validate_treatment(scene.role, treatment, ctx)
    except ValueError as exc:
        raise SpecError(f"{scene.scene_id}: {exc}") from exc

    log.add(scene.scene_id, "accept_treatment", treatment)
    return treatment


def normalize(spec: VideoSpec) -> tuple[VideoSpec, NormalizeLog]:
    """Fill in derived presentation fields. Returns a new spec plus a log."""
    log = NormalizeLog()
    scenes: list[Scene] = []

    for scene in spec.scenes:
        treatment = resolve_treatment(spec, scene, log)
        if treatment != scene.treatment:
            scenes.append(replace(scene, treatment=treatment))
        else:
            scenes.append(scene)

    return replace(spec, scenes=tuple(scenes)), log
