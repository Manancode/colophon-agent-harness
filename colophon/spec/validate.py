"""Structural and referential validation.

Two responsibilities, kept deliberately separate:

``validate``
    Is this spec internally coherent? (references resolve, roles are known,
    durations positive.)

``reject_unknown_keys``
    Does the JSON contain anything the schema does not understand? Colophon
    raises instead of dropping. Rebuilding scenes from a fixed key set
    silently discards everything else, which is exactly how ``treatment``
    vanished the first time we added it. Silent drops are the
    worst failure mode in a system whose whole claim is reproducibility.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Optional

from .schema import (
    ROLES,
    Asset,
    Brand,
    Canvas,
    Claim,
    Scene,
    SpecError,
    Timeline,
    VideoSpec,
)
from ..presentation.treatments import MOTIONS, TREATMENTS, supported_motions

_ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,127}")
_ALLOWED_FPS = frozenset({24, 25, 30, 48, 50, 60})

#: A problem paired with the taxonomy code that classifies it. ``None`` means
#: "not named yet", which the taxonomy treats as a blocker.
#: Spelled with Optional rather than ``str | None`` because this is a runtime
#: expression, and PEP 604 unions only work in annotations before 3.10.
Coded = tuple[Optional[str], str]
_REMOTE = ("http://", "https://", "//", "ftp://", "data:")

_TOP_KEYS = frozenset(
    {
        "spec_version",
        "spec_id",
        "title",
        "canvas",
        "brand",
        "timeline",
        "assets",
        "claims",
        "scenes",
        "notes",
    }
)
_CANVAS_KEYS = frozenset({"width", "height", "fps", "background"})
_BRAND_KEYS = frozenset({"name", "tokens", "voice"})
_TIMELINE_KEYS = frozenset({"policy", "overlap_s", "transition", "transition_ms"})
_ASSET_KEYS = frozenset({"asset_id", "kind", "path", "sha256", "meta"})
_CLAIM_KEYS = frozenset({"claim_id", "text", "kind", "source"})
_SCENE_KEYS = frozenset(
    {
        "scene_id",
        "role",
        "treatment",
        "duration_s",
        "title_claim_id",
        "narration_claim_id",
        "asset_ids",
        "treatment_params",
        "renderer_hints",
    }
)


def reject_unknown_keys(raw: Mapping[str, Any]) -> None:
    """Raise if any key is not part of the schema. Never silently drop."""
    _check(raw, _TOP_KEYS, "spec")
    if "canvas" in raw:
        _check(raw["canvas"], _CANVAS_KEYS, "canvas")
    if isinstance(raw.get("brand"), dict):
        _check(raw["brand"], _BRAND_KEYS, "brand")
    if "timeline" in raw:
        _check(raw["timeline"], _TIMELINE_KEYS, "timeline")
    for i, a in enumerate(raw.get("assets") or ()):
        _check(a, _ASSET_KEYS, f"assets[{i}]")
    for i, c in enumerate(raw.get("claims") or ()):
        _check(c, _CLAIM_KEYS, f"claims[{i}]")
    for i, s in enumerate(raw.get("scenes") or ()):
        _check(s, _SCENE_KEYS, f"scenes[{i}]")


def _check(obj: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    if not isinstance(obj, Mapping):
        raise SpecError(f"{where}: expected an object, got {type(obj).__name__}")
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise SpecError(
            f"{where}: unknown key(s) {unknown}. "
            f"Colophon refuses to drop unknown keys; remove them or extend the schema."
        )


def _check_ids(items: Iterable[Any], attr: str, where: str) -> None:
    seen: set[str] = set()
    for it in items:
        value = getattr(it, attr)
        if not _ID_RE.fullmatch(value):
            raise SpecError(f"{where}: {attr} {value!r} is not a valid id")
        if value in seen:
            raise SpecError(f"{where}: duplicate {attr} {value!r}")
        seen.add(value)


def validate(spec: VideoSpec) -> list[str]:
    """Return a list of problems. Empty list means the spec is valid.

    Returning problems rather than raising on the first one keeps the QA report
    useful: an author fixing a spec wants every issue at once.
    """
    return [message for _, message in validate_coded(spec)]


def validate_coded(spec: VideoSpec) -> list[Coded]:
    """``validate``, but each problem carries its taxonomy code.

    The code is declared here, next to the check that produces it, rather
    than recovered downstream by matching on the message text. A code defined
    far from its check drifts the moment someone rewords the message, and a
    silently-orphaned code blocks every run it touches.
    """
    problems: list[Coded] = []

    if not spec.spec_id.strip():
        problems.append(("spec.id.empty", "spec_id is empty"))
    if not spec.scenes:
        problems.append(("spec.scenes.empty", "spec has no scenes"))

    problems.extend(_validate_canvas(spec.canvas))
    problems.extend(_validate_brand(spec.brand))
    problems.extend(_validate_timeline(spec.timeline))
    problems.extend(_validate_assets(spec.assets))
    problems.extend(_validate_claims(spec.claims))
    problems.extend(_validate_scenes(spec))

    return problems


def assert_valid(spec: VideoSpec) -> None:
    problems = validate(spec)
    if problems:
        raise SpecError("invalid spec:\n  - " + "\n  - ".join(problems))


def _validate_canvas(c: Canvas) -> list[Coded]:
    out: list[Coded] = []
    if c.width <= 0 or c.height <= 0:
        out.append((
            "spec.canvas.dimensions",
            f"canvas dimensions must be positive, got {c.width}x{c.height}",
        ))
    if c.fps not in _ALLOWED_FPS:
        out.append((
            "spec.canvas.fps",
            f"canvas.fps {c.fps} not in {sorted(_ALLOWED_FPS)}",
        ))
    return out


def _validate_brand(b: Brand | None) -> list[Coded]:
    if b is None:
        return [("spec.brand.missing", "brand is missing")]
    out: list[Coded] = []
    if not b.name.strip():
        out.append(("spec.brand.name", "brand.name is empty"))
    for token in Brand.REQUIRED_TOKENS:
        if token not in b.tokens:
            out.append((
                "spec.brand.token",
                f"brand.tokens missing required token {token!r}",
            ))
    return out


def _validate_timeline(t: Timeline) -> list[Coded]:
    out: list[Coded] = []
    if t.policy not in Timeline.POLICIES:
        out.append((
            "spec.timeline.policy",
            f"timeline.policy {t.policy!r} not in {list(Timeline.POLICIES)}",
        ))
    if t.policy == "explicit":
        out.append((
            "spec.timeline.policy",
            "timeline.policy 'explicit' is not supported in V0",
        ))
    if t.transition not in Timeline.TRANSITIONS:
        out.append((
            "spec.timeline.transition",
            f"timeline.transition {t.transition!r} not in {list(Timeline.TRANSITIONS)}",
        ))
    if t.transition_ms < 0:
        out.append((
            "spec.timeline.transition_ms",
            "timeline.transition_ms must be >= 0",
        ))
    if t.overlap_s < 0:
        out.append((
            "spec.timeline.overlap_s",
            "timeline.overlap_s must be >= 0",
        ))
    if t.transition == "match_cut" and t.overlap_s <= 0:
        # A match cut joins two scenes *through* the frames they share. With no
        # overlap there is nothing to cross-cut with, so the choice is
        # incoherent rather than merely unusual.
        out.append((
            "spec.timeline.match_cut_needs_overlap",
            "timeline.transition 'match_cut' requires timeline.overlap_s > 0 "
            "(a match cut needs shared frames to cut across)",
        ))
    return out


def _validate_assets(assets: tuple[Asset, ...]) -> list[Coded]:
    out: list[Coded] = []
    try:
        _check_ids(assets, "asset_id", "assets")
    except SpecError as exc:
        out.append(("spec.asset.id_duplicate", str(exc)))
    for a in assets:
        if a.kind not in Asset.KINDS:
            out.append((
                "spec.asset.kind",
                f"asset {a.asset_id}: kind {a.kind!r} not in {list(Asset.KINDS)}",
            ))
        if any(a.path.startswith(p) for p in _REMOTE):
            out.append((
                "spec.asset.remote",
                f"asset {a.asset_id}: remote assets are not permitted ({a.path})",
            ))
        if not a.path.strip():
            out.append(("spec.asset.path", f"asset {a.asset_id}: path is empty"))
    return out


def _validate_claims(claims: tuple[Claim, ...]) -> list[Coded]:
    out: list[Coded] = []
    try:
        _check_ids(claims, "claim_id", "claims")
    except SpecError as exc:
        out.append(("spec.claim.id_duplicate", str(exc)))
    for c in claims:
        if c.kind not in Claim.KINDS:
            out.append((
                "spec.claim.kind",
                f"claim {c.claim_id}: kind {c.kind!r} not in {list(Claim.KINDS)}",
            ))
        if not c.text.strip():
            out.append(("spec.claim.text", f"claim {c.claim_id}: text is empty"))
    return out


def _validate_scenes(spec: VideoSpec) -> list[Coded]:
    out: list[Coded] = []
    try:
        _check_ids(spec.scenes, "scene_id", "scenes")
    except SpecError as exc:
        out.append(("spec.scene.id_duplicate", str(exc)))

    claim_ids = {c.claim_id for c in spec.claims}
    asset_ids = {a.asset_id for a in spec.assets}

    for s in spec.scenes:
        where = f"scene {s.scene_id}"
        if s.role not in ROLES:
            out.append(("spec.scene.role", f"{where}: role {s.role!r} not in {list(ROLES)}"))
        if not s.treatment.strip():
            out.append(("spec.scene.treatment", f"{where}: treatment is empty"))
        if s.motion not in MOTIONS:
            out.append((
                "spec.scene.motion",
                f"{where}: motion {s.motion!r} is not in {list(MOTIONS)}",
            ))
        # A motion is only real if the renderer emits the element it targets.
        # stat-hero builds its own <h1 class="figure"> and never calls
        # _title(), so word-sweep there emitted no word spans at all: accepted,
        # rendered, and silently inert. Rejecting the pair here converts an
        # invisible no-op into a spec error the author sees immediately.
        elif s.treatment in TREATMENTS:
            allowed = supported_motions(s.treatment)
            if s.motion not in allowed:
                out.append((
                    "spec.scene.motion_unsupported",
                    f"{where}: treatment {s.treatment!r} does not support motion "
                    f"{s.motion!r} (supported: {', '.join(allowed)})",
                ))
        if s.duration_s <= 0:
            out.append((
                "spec.scene.duration",
                f"{where}: duration_s must be > 0, got {s.duration_s}",
            ))

        for attr, cid in (
            ("title_claim_id", s.title_claim_id),
            ("narration_claim_id", s.narration_claim_id),
        ):
            if cid is not None and cid not in claim_ids:
                out.append((
                    "spec.scene.claim_ref",
                    f"{where}: {attr} references unknown claim {cid!r}",
                ))

        title = spec.claim(s.title_claim_id)
        if title is not None and title.kind != "title":
            out.append((
                "spec.scene.title_claim_kind",
                f"{where}: title_claim_id points at {title.claim_id} "
                f"whose kind is {title.kind!r}, expected 'title'",
            ))

        for aid in s.asset_ids:
            if aid not in asset_ids:
                out.append((
                    "spec.scene.asset_ref",
                    f"{where}: references unknown asset {aid!r}",
                ))

    # every claim should be used by something, otherwise it is dead weight
    used = {cid for s in spec.scenes for cid in (s.title_claim_id, s.narration_claim_id)}
    for c in spec.claims:
        if c.claim_id not in used:
            out.append((
                "spec.claim.unreferenced",
                f"claim {c.claim_id} is not referenced by any scene",
            ))

    return out
