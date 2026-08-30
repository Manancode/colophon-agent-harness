"""The hash-bound review context.

A visual review is only worth anything if it is a review *of a specific
artifact*. This module produces the object that makes that enforceable:
every artifact and every preview is hashed, and the whole thing is folded
into one ``review_context_sha256`` that the reviewer must copy back
unchanged.

That single binding closes four ways a review can be quietly worthless:

* **Replay.** A glowing review of attempt 03 cannot be attached to attempt
  04 — the context hash differs.
* **Partial review.** ``preview_ids`` is the *complete* sorted set of
  previews. A reviewer must echo all of them back, so "I looked at the
  contact sheet" is not a review of six frames.
* **Swap.** Paths are hashed at build time and again when the review is
  recorded, so an artifact cannot be swapped in between.
* **Rubric drift.** The rubric hash is inside the context, so a review
  recorded against an older rubric is rejected rather than silently
  reinterpreted.

Symlinked and hard-linked paths are refused outright. A link can be
re-pointed after hashing, which would let a review bind to bytes it never
looked at.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..qa.rubric import rubric_sha256
from ..spec.hash import sha256_file

CONTEXT_FORMAT_VERSION = 1


class ContextError(RuntimeError):
    """The review context could not be built or does not validate."""


def hash_material(path: str | Path) -> str:
    """Hash a file, refusing links.

    ``st_nlink != 1`` also refuses hard links, which share the same
    exposure: the reviewer hashes one inode and a later read follows
    another.
    """
    p = Path(path)
    if p.is_symlink():
        raise ContextError(f"refusing to hash a symlink: {p}")
    if not p.is_file():
        raise ContextError(f"review material is missing: {p}")
    if p.stat().st_nlink != 1:
        raise ContextError(f"refusing to hash a linked file: {p}")
    return sha256_file(str(p))


@dataclass(frozen=True)
class ReviewContext:
    attempt_id: str
    spec_sha256: str
    rubric_sha256: str
    artifact_hashes: dict[str, str] = field(default_factory=dict)
    preview_hashes: dict[str, str] = field(default_factory=dict)
    preview_ids: list[str] = field(default_factory=list)
    review_context_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": CONTEXT_FORMAT_VERSION,
            "attempt_id": self.attempt_id,
            "spec_sha256": self.spec_sha256,
            "rubric_sha256": self.rubric_sha256,
            "artifact_hashes": dict(self.artifact_hashes),
            "preview_hashes": dict(self.preview_hashes),
            "preview_ids": list(self.preview_ids),
            "review_context_sha256": self.review_context_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReviewContext":
        return cls(
            attempt_id=str(data["attempt_id"]),
            spec_sha256=str(data["spec_sha256"]),
            rubric_sha256=str(data["rubric_sha256"]),
            artifact_hashes=dict(data.get("artifact_hashes") or {}),
            preview_hashes=dict(data.get("preview_hashes") or {}),
            preview_ids=list(data.get("preview_ids") or []),
            review_context_sha256=str(data.get("review_context_sha256") or ""),
        )


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_review_context(
    *,
    attempt_id: str,
    spec_sha256: str,
    video: str | Path,
    frames: list[Path],
    contact_sheet: str | Path | None = None,
    extra_artifacts: Mapping[str, str | Path] | None = None,
) -> ReviewContext:
    """Hash every artifact and preview, then bind them into one digest."""
    artifact_hashes: dict[str, str] = {"video": hash_material(video)}
    for name, path in (extra_artifacts or {}).items():
        artifact_hashes[name] = hash_material(path)

    preview_hashes: dict[str, str] = {}
    if contact_sheet is not None:
        preview_hashes["contact_sheet"] = hash_material(contact_sheet)
    for i, frame in enumerate(sorted(frames, key=lambda p: p.name), start=1):
        preview_hashes[f"frame_{i:02d}"] = hash_material(frame)

    if not preview_hashes:
        raise ContextError("no previews to review; extract frames first")

    preview_ids = sorted(preview_hashes)
    context_sha = _digest(
        {
            "format_version": CONTEXT_FORMAT_VERSION,
            "attempt_id": attempt_id,
            "spec_sha256": spec_sha256,
            "rubric_sha256": rubric_sha256(),
            "artifact_hashes": artifact_hashes,
            "preview_hashes": preview_hashes,
        }
    )
    return ReviewContext(
        attempt_id=attempt_id,
        spec_sha256=spec_sha256,
        rubric_sha256=rubric_sha256(),
        artifact_hashes=artifact_hashes,
        preview_hashes=preview_hashes,
        preview_ids=preview_ids,
        review_context_sha256=context_sha,
    )


def write_review_context(context: ReviewContext, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(context.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def read_review_context(path: str | Path) -> ReviewContext:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ContextError(f"review context must be an object: {path}")
    if data.get("format_version") != CONTEXT_FORMAT_VERSION:
        raise ContextError(
            f"unsupported review context format "
            f"{data.get('format_version')!r}; expected {CONTEXT_FORMAT_VERSION}"
        )
    return ReviewContext.from_dict(data)


def validate_context(context: ReviewContext, *, expected_rubric: str | None = None) -> None:
    """Re-check the binding. Called again at record time, not just build time."""
    if not context.preview_ids:
        raise ContextError("review context has no previews")
    if sorted(context.preview_hashes) != sorted(context.preview_ids):
        raise ContextError(
            "preview_ids does not match the preview set: "
            f"{sorted(context.preview_ids)} vs {sorted(context.preview_hashes)}"
        )
    expected_rubric = expected_rubric or rubric_sha256()
    if context.rubric_sha256 != expected_rubric:
        raise ContextError(
            "review context was built against a different rubric "
            f"({context.rubric_sha256[:12]}); current rubric is "
            f"{expected_rubric[:12]}"
        )
    recomputed = _digest(
        {
            "format_version": CONTEXT_FORMAT_VERSION,
            "attempt_id": context.attempt_id,
            "spec_sha256": context.spec_sha256,
            "rubric_sha256": context.rubric_sha256,
            "artifact_hashes": context.artifact_hashes,
            "preview_hashes": context.preview_hashes,
        }
    )
    if recomputed != context.review_context_sha256:
        raise ContextError(
            "review context digest does not match its contents; the context "
            "was edited after it was built"
        )
