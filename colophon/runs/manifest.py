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
    from ..spec.hash import sha256_file

    try:
        expected = paths.spec_hash.read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError):
        return None

    candidates: list[int] = []
    for number in sorted(
        (int(p.name) for p in paths.attempts.iterdir() if p.is_dir() and p.name.isdigit()),
        reverse=True,
    ):
        attempt = AttemptPaths(
            root=paths.attempts / f"{number:02d}",
            project=paths.attempts / f"{number:02d}" / "project",
            artifact=paths.attempts / f"{number:02d}" / "artifact",
            qa=paths.attempts / f"{number:02d}" / "qa",
            review=paths.attempts / f"{number:02d}" / "review",
        )
        manifest = read_manifest(attempt)
        if manifest is None or manifest.spec_sha256 != expected:
            continue
        video = attempt.artifact / "launch-video.mp4"
        if video.is_file() and video.stat().st_size > 0:
            candidates.append(number)
    return candidates[0] if candidates else None
