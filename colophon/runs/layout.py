"""Run directory layout.

A run is a complete, self-describing record: the frozen spec, every attempt,
every QA report, every review. Given a run directory and the pinned runtime,
the video is reproducible.

    <run_dir>/
      spec.json            the frozen canonical spec (never rewritten)
      spec.sha256          its fingerprint, for a one-line integrity check
      runtime-state.json   resolved tools and versions
      attempts/
        01/
          project/         the emitted, editable video project
          artifact/        the MP4 and the delivery report
          qa/              stage results
          review/          extracted frames, contact sheet, review records
        02/                a repair attempt
      final/               symlink-or-copy of the accepted attempt

The spec is written once and never touched again. Attempts only ever *read*
it, which is what makes "which spec made this video?" answerable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..spec.hash import spec_sha256
from ..spec.io import save, write_json
from ..spec.schema import VideoSpec

ATTEMPT_DIRNAME = "attempts"
PROJECT_DIRNAME = "project"
ARTIFACT_DIRNAME = "artifact"
QA_DIRNAME = "qa"
REVIEW_DIRNAME = "review"
FINAL_DIRNAME = "final"


@dataclass(frozen=True)
class AttemptPaths:
    root: Path
    project: Path
    artifact: Path
    qa: Path
    review: Path

    def to_dict(self) -> dict[str, Any]:
        return {k: str(v) for k, v in self.__dict__.items()}


@dataclass(frozen=True)
class RunPaths:
    root: Path
    spec: Path
    spec_hash: Path
    runtime_state: Path
    attempts: Path
    final: Path
    runtime: Path

    def to_dict(self) -> dict[str, Any]:
        return {k: str(v) for k, v in self.__dict__.items()}


def run_paths(run_dir: str | Path) -> RunPaths:
    root = Path(run_dir).resolve()
    return RunPaths(
        root=root,
        spec=root / "spec.json",
        spec_hash=root / "spec.sha256",
        runtime_state=root / "runtime-state.json",
        attempts=root / ATTEMPT_DIRNAME,
        final=root / FINAL_DIRNAME,
        runtime=root / "runtime",
    )


def init_run(run_dir: str | Path, spec: VideoSpec) -> RunPaths:
    """Create the run directory and freeze the spec into it."""
    paths = run_paths(run_dir)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.attempts.mkdir(exist_ok=True)
    paths.final.mkdir(exist_ok=True)
    paths.runtime.mkdir(exist_ok=True)

    save(spec, paths.spec)
    digest = spec_sha256(spec)
    paths.spec_hash.write_text(f"{digest}  spec.json\n", encoding="utf-8")
    return paths


def load_spec(paths: RunPaths) -> VideoSpec:
    from ..spec.io import load

    return load(paths.spec)


def next_attempt(paths: RunPaths) -> int:
    """The number the next attempt should get."""
    existing = [p.name for p in paths.attempts.iterdir() if p.is_dir()]
    numbers = [int(n) for n in existing if n.isdigit()]
    return (max(numbers) + 1) if numbers else 1


def begin_attempt(paths: RunPaths, number: int | None = None) -> AttemptPaths:
    n = number if number is not None else next_attempt(paths)
    root = paths.attempts / f"{n:02d}"
    attempt = AttemptPaths(
        root=root,
        project=root / PROJECT_DIRNAME,
        artifact=root / ARTIFACT_DIRNAME,
        qa=root / QA_DIRNAME,
        review=root / REVIEW_DIRNAME,
    )
    for d in (attempt.project, attempt.artifact, attempt.qa, attempt.review):
        d.mkdir(parents=True, exist_ok=True)
    return attempt


def list_attempts(paths: RunPaths) -> list[int]:
    return sorted(
        int(p.name) for p in paths.attempts.iterdir() if p.is_dir() and p.name.isdigit()
    )


def latest_attempt(paths: RunPaths) -> int | None:
    attempts = list_attempts(paths)
    return attempts[-1] if attempts else None


def promote(paths: RunPaths, attempt_number: int) -> Path:
    """Mark an attempt as the accepted deliverable.

    Copies rather than symlinks so the final artifact survives the run
    directory being moved or archived.
    """
    import shutil

    src = paths.attempts / f"{attempt_number:02d}" / ARTIFACT_DIRNAME
    if not src.is_dir():
        raise FileNotFoundError(f"attempt {attempt_number} has no artifact directory")
    dst = paths.final
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    write_json({"accepted_attempt": attempt_number}, paths.final / "final.json")
    return dst
