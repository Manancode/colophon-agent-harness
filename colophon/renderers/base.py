"""The renderer adapter contract.

A renderer adapter is the only place in Colophon allowed to know what HTML and
CSS are. Everything upstream deals in the canonical spec; everything downstream
deals in an MP4 plus a report.

The two-phase split is the important part:

    emit(spec)   -> an editable video project on disk
    render(...)  -> an MP4 from that project

Keeping them apart is what makes "editable video project" a real deliverable
rather than a slogan, and what lets QA inspect the project before spending
render time on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..assets.registry import AssetRegistry
from ..spec.schema import VideoSpec
from ..timeline.plan import TimelinePlan


@dataclass(frozen=True)
class ToolRequirement:
    """An executable the renderer needs from the runtime."""

    name: str
    min_version: str = ""
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "min_version": self.min_version, "required": self.required}


@dataclass
class RenderContext:
    """Everything an adapter is allowed to see about a run."""

    spec: VideoSpec
    plan: TimelinePlan
    project_dir: Path
    out_dir: Path
    assets: AssetRegistry | None = None
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def spec_sha256(self) -> str:
        from ..spec.hash import spec_sha256

        return spec_sha256(self.spec)


@dataclass
class EmitResult:
    """What ``emit`` produced."""

    project_dir: Path
    entry: Path
    #: raw markup per scene, so QA can ground-check without re-rendering
    scene_fragments: dict[str, str] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        # scene_fragments is persisted, not just summarised: `colophon qa` is a
        # separate process from `colophon emit` and re-derives nothing. Dropping
        # the markup here left the grounding stage permanently reporting "no
        # emitted fragments to check" whenever QA ran on its own.
        return {
            "project_dir": str(self.project_dir),
            "entry": str(self.entry),
            "scene_ids": sorted(self.scene_fragments),
            "scene_fragments": dict(self.scene_fragments),
            "files": list(self.files),
            "warnings": list(self.warnings),
        }


@dataclass
class RenderResult:
    """What ``render`` produced, and everything needed to say why it failed.

    ``exit_code`` and ``diagnostics`` exist because of a real failure: a render
    that produced ``error: render failed:`` with no message at all. The adapter
    had captured stdout and stderr, both were empty, and the actual cause was
    that the renderer exited 0 without writing the output file. Nothing in the
    result said so.

    The lesson: a renderer can fail without writing to stderr, so a
    ``RenderResult`` must carry the *observed filesystem state* alongside the
    process output, and failure reporting must never depend on a single stream
    being non-empty.
    """

    ok: bool
    video_path: Path | None = None
    command: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    duration_s: float | None = None
    warnings: list[str] = field(default_factory=list)
    #: process exit status; None when the process never ran
    exit_code: int | None = None
    #: observed filesystem state and other facts gathered after the run
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "video_path": str(self.video_path) if self.video_path else None,
            "command": list(self.command),
            "stdout_tail": self.stdout[-4000:],
            "stderr_tail": self.stderr[-4000:],
            "duration_s": self.duration_s,
            "warnings": list(self.warnings),
            "exit_code": self.exit_code,
            "diagnostics": dict(self.diagnostics),
        }

    def describe_failure(self) -> str:
        """A complete, non-empty account of why the render failed.

        Deliberately concatenates every stream rather than picking one: the
        failure this exists for had an empty stderr and an empty stdout.
        """
        lines = [f"exit code: {self.exit_code}"]

        for label, blob in (("stdout", self.stdout), ("stderr", self.stderr)):
            tail = (blob or "").strip()[-2000:]
            lines.append(f"{label}: {tail if tail else '(empty)'}")

        for key, value in sorted(self.diagnostics.items()):
            lines.append(f"{key}: {value}")

        if self.warnings:
            lines.append("warnings: " + "; ".join(self.warnings))

        return "\n  ".join(lines)


class AdapterError(RuntimeError):
    """Raised when a renderer cannot do what was asked of it."""


@runtime_checkable
class RendererAdapter(Protocol):
    """Interface every renderer must satisfy.

    Deliberately small. Adding a renderer should mean writing ``emit`` and
    ``render``, nothing else.
    """

    #: short identifier recorded in reports, e.g. "hyperframes"
    name: str
    #: pinned renderer version, e.g. "0.7.86"
    version: str

    def runtime_requirements(self) -> list[ToolRequirement]:
        """Executables and packages this renderer needs."""

    def emit(self, ctx: RenderContext) -> EmitResult:
        """Turn the spec into an editable project on disk."""

    def render(self, ctx: RenderContext, emit_result: EmitResult) -> RenderResult:
        """Turn the emitted project into an MP4."""


def get_adapter(name: str) -> "RendererAdapter":
    """Instantiate a renderer adapter by name."""
    key = (name or "").strip().lower()
    if key in ("hyperframes", "hf"):
        from .hyperframes import adapter as hf

        return hf.HyperFramesAdapter()
    raise AdapterError(f"unknown renderer {name!r}; known: hyperframes, hf")
