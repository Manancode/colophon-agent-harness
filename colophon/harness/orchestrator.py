"""Phase 6 orchestration: run the design loop with the renderer wired in.

This is the thin convenience layer that ties the design-harness loop
(``designer.run_design_loop``) to the render driver (``render.RuntimeRenderDriver``).
It exists so the CLI and callers do not have to know how capability detection,
workspace provisioning, and graceful degradation fit together -- they ask for a
driver and run the loop, and the rest is handled by the seam.

Plain English: ``make_runtime_driver`` builds the thing that can actually make a
video; ``design_and_render`` runs the repair loop with that driver attached, so
the loop both fixes the spec *and* checks the rendered video. When the renderer
cannot run in this environment the loop degrades to spec-level and records an
attestation -- nothing here forces a network call or a broken run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .designer import DesignerSettings, run_design_loop
from .render import (
    RenderCapability,
    RenderDriver,
    RuntimeRenderDriver,
    resolve_render_capability,
)


def make_runtime_driver(
    renderer: str = "hyperframes", workspace: Any | None = None
) -> RuntimeRenderDriver:
    """Build a renderer driver for the loop.

    ``workspace`` is where attempt directories are written; pass a stable path
    (e.g. inside a run directory) to keep the produced artifacts inspectable,
    or leave it ``None`` for a one-off temp directory.
    """
    return RuntimeRenderDriver(adapter_name=renderer)


def capability() -> RenderCapability:
    """Probe whether a real render is possible, without rendering."""
    return resolve_render_capability()


def design_and_render(
    spec: Any,
    *,
    renderer: str = "hyperframes",
    workspace: Any | None = None,
    llm: Any | None = None,
    contract: Any | None = None,
    settings: DesignerSettings | None = None,
) -> Any:
    """Run the design loop with a real renderer wired in.

    Equivalent to ``run_design_loop(spec, driver=make_runtime_driver(...))`` with
    the workspace threaded through. If the renderer cannot produce a video the
    loop still completes at the spec level and records the reason in the
    session's ``render_attestation``.
    """
    driver = make_runtime_driver(renderer=renderer, workspace=workspace)
    return run_design_loop(
        spec,
        llm=llm,
        contract=contract,
        settings=settings,
        driver=driver,
        workspace=Path(workspace) if workspace is not None else None,
    )
