"""Attempt manifest, delivery reports and recovery.

Every attempt writes a manifest describing what it did and what came of it.
That is what makes a run resumable: ``resume`` reads the manifests, finds the
last attempt that produced a usable artifact, and carries on from there
instead of starting over.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..spec.hash import scene_hashes, spec_sha256
from ..spec.schema import VideoSpec
from .layout import AttemptPaths, RunPaths


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class AttemptManifest:
    attempt: int
    created_at: str = field(default_factory=_now)
    spec_sha256: str = ""
    renderer: str = ""
    renderer_version: str = ""
    scene_hashes: dict[str, str] = field(default_factory=dict)
    qa_passed: bool | None = None
    qa_stages: list[dict[str, Any]] = field(default_factory=list)
    video: str | None = None
    video_sha256: str | None = None
    repair_of: int | None = None
    repairs: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_manifest(attempt: AttemptPaths, manifest: AttemptManifest) -> Path:
    path = attempt.root / "manifest.json"
    path.write_text(json.dumps(manifest.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def read_manifest(attempt: AttemptPaths) -> AttemptManifest | None:
    path = attempt.root / "manifest.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    known = {f for f in AttemptManifest.__dataclass_fields__}
    return AttemptManifest(**{k: v for k, v in raw.items() if k in known})


def new_manifest(
    attempt_number: int,
    spec: VideoSpec,
    *,
    renderer: str,
    renderer_version: str,
    repair_of: int | None = None,
) -> AttemptManifest:
    return AttemptManifest(
        attempt=attempt_number,
        spec_sha256=spec_sha256(spec),
        renderer=renderer,
        renderer_version=renderer_version,
        scene_hashes=scene_hashes(spec),
        repair_of=repair_of,
    )


@dataclass
class DeliveryReport:
    """The artifact a run hands over. Everything here is traceable."""

    run_dir: str
    attempt: int
    spec_sha256: str
    scene_hashes: dict[str, str]
    renderer: str
    renderer_version: str
    passed: bool
    stages: list[dict[str, Any]]
    video: str | None = None
    video_sha256: str | None = None
    planned_duration_s: float | None = None
    rendered_duration_s: float | None = None
    reviews: list[dict[str, Any]] = field(default_factory=list)
    repairs: list[dict[str, Any]] = field(default_factory=list)
    runtime: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_delivery_report(attempt: AttemptPaths, report: DeliveryReport) -> Path:
    path = attempt.artifact / "delivery-report.json"
    path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def read_delivery_report(attempt: AttemptPaths) -> dict[str, Any] | None:
    path = attempt.artifact / "delivery-report.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def resumable_attempt(paths: RunPaths) -> int | None:
    """The most recent attempt that still has a real, matching spec.

    An attempt whose spec hash no longer matches the run's frozen spec is
    stale — the spec moved on — so it cannot be resumed, only superseded.
    """
    from ..runs import layout as run_layout

    try:
        expected = paths.spec_hash.read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError):
        return None

    for number in sorted(run_layout.list_attempts(paths), reverse=True):
        attempt = run_layout.attempt_paths(paths, number)
        manifest = read_manifest(attempt)
        if manifest is None or manifest.spec_sha256 != expected:
            continue
        video = attempt.artifact / "launch-video.mp4"
        if video.is_file() and video.stat().st_size > 0:
            return number
    return None


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------
#
# A verdict is only honest if the artifact it describes was made from the spec
# it names. An attempt that predates the current spec is not a candidate for
# evaluation at all: its project and its MP4 were emitted from something else,
# and writing the current hash into its report would attest to a video that
# hash never produced.

#: No artifact yet. Nothing exists to misattest, so the gates may run — they
#: report "nothing to check", which is the useful answer before an emit.
PROVENANCE_EMPTY = "empty"

#: The manifest names this exact spec. Safe to evaluate.
PROVENANCE_MATCHES = "matches"

#: The manifest names a different spec. Never safe to evaluate.
PROVENANCE_STALE = "stale"

#: Artifacts exist but no manifest says which spec made them. Fails closed.
PROVENANCE_UNKNOWN = "unknown"


class StaleArtifactError(Exception):
    """An attempt's artifacts belong to a spec other than the run's."""


def attempt_provenance(attempt: AttemptPaths, expected: str) -> str:
    """Whether this attempt's artifacts may be attested against ``expected``.

    The distinction that matters is between *having nothing* and *having the
    wrong thing*. An attempt that was never emitted has no artifact, so there
    is no false claim to make — running the gates on it is what tells an agent
    "emit first". An attempt holding a project or a video needs its manifest to
    vouch for that artifact, and without one the only safe answer is refusal.
    """
    has_artifact = any(
        p.is_file() and p.stat().st_size > 0
        for p in (
            attempt.artifact / "launch-video.mp4",
            attempt.project / "index.html",
        )
    )
    manifest = read_manifest(attempt)
    if manifest is None or not manifest.spec_sha256:
        return PROVENANCE_UNKNOWN if has_artifact else PROVENANCE_EMPTY
    if manifest.spec_sha256 == expected:
        return PROVENANCE_MATCHES
    return PROVENANCE_STALE


def evaluable_attempt(
    paths: RunPaths, expected: str, number: int | None = None
) -> int:
    """The attempt whose artifacts may be attested against ``expected``.

    With ``number`` given, that attempt is checked on its own and refused if
    it is stale or unmanifested. Without one, the most recent attempt that is
    safe to evaluate wins — later than any empty attempt, since an attempt
    with a matching artifact is a better answer than one with nothing in it.

    Raises :class:`StaleArtifactError` when nothing qualifies, and
    ``FileNotFoundError`` when the run has no attempts at all.
    """
    from ..runs import layout as run_layout

    attempts = run_layout.list_attempts(paths)
    if number is not None:
        candidates = [number]
    elif attempts:
        candidates = sorted(attempts, reverse=True)
    else:
        raise FileNotFoundError(
            f"no attempts in {paths.attempts}; emit a project first, then "
            f"run this again"
        )

    usable: list[int] = []
    rejections: list[str] = []
    for n in candidates:
        attempt = run_layout.attempt_paths(paths, n)
        state = attempt_provenance(attempt, expected)
        if state in (PROVENANCE_EMPTY, PROVENANCE_MATCHES):
            usable.append(n)
        elif state == PROVENANCE_STALE:
            manifest = read_manifest(attempt)
            rejections.append(
                f"attempt {n:02d} was emitted from spec "
                f"{manifest.spec_sha256[:12]}, but this run is now "
                f"{expected[:12]} — its artifacts predate the current spec, "
                f"so no verdict written here could honestly describe them"
            )
        else:
            rejections.append(
                f"attempt {n:02d} holds a project or video but has no "
                f"manifest naming the spec that made it, so its provenance "
                f"cannot be proven"
            )

    if usable:
        # Prefer an attempt with real, matching artifacts over a bare one.
        matching = [
            n
            for n in usable
            if attempt_provenance(run_layout.attempt_paths(paths, n), expected)
            == PROVENANCE_MATCHES
        ]
        return max(matching) if matching else usable[0]

    raise StaleArtifactError(
        (
            f"no attempt in {paths.attempts} can be evaluated against spec "
            f"{expected[:12]}. "
        )
        + "; ".join(rejections[:3])
        + ". Re-emit from the current spec, or start a new run directory."
    )
