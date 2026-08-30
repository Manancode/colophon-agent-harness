"""Render driver for the design-harness loop (Phase 6 orchestration).

Phase 5 ran the *spec-level* gates and mechanically fixed what it could.
Phase 6 lets the loop drive the real pipeline -- emit the editable project,
render it to an MP4, and run the *full* gate set (static HTML, scene
structure, media contract, motion velocity, ...) on the actual artifact, then
feed those findings back into the same repair router.

The renderer is a *seam*, not a dependency. Three things keep that honest:

* ``RenderDriver`` is a protocol. The default is ``NoRenderDriver`` (no
  renderer wired), in which case the loop is exactly Phase 5: spec-level,
  deterministic, no network, no encoder.
* ``RuntimeRenderDriver`` talks to the real renderer (HyperFrames via
  ``get_adapter``). Because a real render is expensive and needs the runtime,
  it *degrades gracefully*: if the runtime or the renderer is missing it
  declines (``rendered=False``) and the loop falls back to spec-level with an
  attestation rather than crashing or silently shipping.
* The driver never auto-installs the renderer mid-loop. Provisioning
  (``npm install`` of the pinned HyperFrames) is a one-time, explicit step
  done by ``colophon render`` / ``colophon deliver``; the loop reuses the
  installed binary so it can never trigger a per-turn network install or
  vary between turns.

Plain English: the loop asks the driver "can you actually make the video?"
If yes, it checks the video and fixes what it can. If no, it checks the spec
as far as it can and tells you plainly that the full video QA did not run.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..spec.schema import VideoSpec
from ..timeline.plan import TimelinePlan


@dataclass
class RenderCapability:
    """Whether a real render can happen in this environment right now."""

    available: bool
    reason: str
    missing: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "missing": list(self.missing),
        }


def resolve_render_capability() -> RenderCapability:
    """Probe node / npm / ffmpeg / ffprobe without rendering anything.

    This is the cheap, safe half of "can we render?": it asks whether the
    executables exist. Actually producing a video is the driver's job and is
    gated further on the renderer being provisioned. Keeping the probe here,
    separate from the heavy import in the driver, means capability checks
    never pull in the renderer.
    """
    from ..runtime import tools

    found = tools.resolve_runtime()
    missing = tuple(name for name, t in found.items() if not t.found)
    if missing:
        return RenderCapability(
            available=False,
            reason=(
                "runtime missing tools: " + ", ".join(missing) +
                "; render-dependent gates skipped"
            ),
            missing=missing,
        )
    return RenderCapability(
        available=True,
        reason="node, npm, ffmpeg and ffprobe all resolved",
        missing=(),
    )


@dataclass
class RenderOutcome:
    """What a render attempt produced, plus the artifacts QA needs.

    ``rendered`` is the contract the loop keys on. ``True`` means the driver
    produced a real artifact and ``context`` carries what the full gate set
    needs (``document``, ``scene_fragments``, ``video_path``,
    ``project_dir``, ``rendered_duration_s``). ``False`` means it could not
    (runtime absent, renderer not provisioned, encode failed) and ``context``
    is empty, so the loop knows to fall back to spec-level gates rather than
    point the QA stages at ``None`` (which would spuriously block).
    """

    rendered: bool
    context: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    attempt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rendered": self.rendered,
            "error": self.error,
            "attempt": self.attempt,
            "context_keys": sorted(self.context),
        }


class RenderDriver(Protocol):
    """Integration point for turning a spec into a real video.

    Implement this to wire a renderer. Return ``rendered=False`` (with a
    reason) whenever a real encode is not possible; the loop handles that
    gracefully instead of assuming a video exists.
    """

    def render(
        self, *, spec: VideoSpec, plan: TimelinePlan, workspace: Path | None
    ) -> RenderOutcome:
        ...


@dataclass
class NoRenderDriver:
    """The default seam: no renderer wired, so rendering never happens."""

    def render(
        self, *, spec: VideoSpec, plan: TimelinePlan, workspace: Path | None
    ) -> RenderOutcome:
        return RenderOutcome(
            rendered=False, context={}, error="no render driver configured"
        )


@dataclass
class RuntimeRenderDriver:
    """Talk to the real renderer (HyperFrames) without auto-installing it.

    The driver reuses a *provisioned* binary. Provisioning (``npm install``)
    is done once by ``colophon render`` / ``colophon deliver``; the loop will
    not reach for the network, so it can never stall or vary between turns.
    """

    adapter_name: str = "hyperframes"
    _attempt: int = 0
    #: Resolved once per driver so a loop that re-evaluates several times per
    #: turn reuses one workspace instead of minting a temp directory per call.
    _base: Path | None = field(default=None, init=False, repr=False)

    def render(
        self, *, spec: VideoSpec, plan: TimelinePlan, workspace: Path | None
    ) -> RenderOutcome:
        cap = resolve_render_capability()
        if not cap.available:
            return RenderOutcome(rendered=False, context={}, error=cap.reason)

        from ..renderers.base import RenderContext, get_adapter

        adapter = get_adapter(self.adapter_name)
        project_dir, out_dir = self._workspace_dirs(workspace)
        ctx = RenderContext(
            spec=spec, plan=plan, project_dir=project_dir, out_dir=out_dir
        )

        # Reuse an already-installed binary; never install per turn.
        try:
            binary = adapter.hyperframes_binary(ctx)
        except Exception as exc:  # noqa: BLE001 - report, don't crash the loop
            return RenderOutcome(
                rendered=False,
                context={},
                error=f"could not locate renderer binary: {exc}",
                attempt=str(project_dir),
            )

        if not binary.exists():
            return RenderOutcome(
                rendered=False,
                context={},
                error=(
                    f"renderer not provisioned at {binary}; run "
                    f"`colophon render` (or `colophon deliver`) once to install "
                    f"{self.adapter_name} before using `colophon design --render`"
                ),
                attempt=str(project_dir),
            )

        try:
            emit_result = adapter.emit(ctx)
            document = (project_dir / "index.html").read_text(encoding="utf-8")
            render_result = adapter.render(ctx, emit_result)
        except Exception as exc:  # noqa: BLE001 - report, don't crash the loop
            return RenderOutcome(
                rendered=False,
                context={},
                error=f"render driver failed: {type(exc).__name__}: {exc}",
                attempt=str(project_dir),
            )

        if not render_result.ok:
            return RenderOutcome(
                rendered=False,
                context={},
                error=render_result.describe_failure(),
                attempt=str(project_dir),
            )

        return RenderOutcome(
            rendered=True,
            context={
                "document": document,
                "scene_fragments": dict(emit_result.scene_fragments),
                "video_path": render_result.video_path,
                "project_dir": project_dir,
                "rendered_duration_s": render_result.duration_s,
            },
            attempt=str(project_dir),
        )

    def _workspace_dirs(self, workspace: Path | None):
        """A fresh attempt directory so each loop turn renders in isolation.

        The *base* is resolved once per driver and cached: the loop calls this
        several times per turn (once per evaluation), and minting a temp root
        each time would scatter a run's artifacts across unrelated directories
        instead of keeping them together for inspection.
        """
        if self._base is None:
            if workspace is None:
                self._base = Path(tempfile.mkdtemp(prefix="colophon-design-"))
            else:
                self._base = Path(workspace)
        base = self._base
        base.mkdir(parents=True, exist_ok=True)
        self._attempt += 1
        attempt = base / f"attempt-{self._attempt:02d}"
        project_dir = attempt / "project"
        out_dir = attempt / "artifact"
        project_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        return project_dir, out_dir
