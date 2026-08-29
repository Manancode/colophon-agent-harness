"""HyperFrames adapter — the first renderer Colophon supports."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ...runtime import tools as _tools
from ...runtime.tools import ToolError, run
from ...spec.hash import sha256_file
from ...spec.schema import VideoSpec
from ..base import (
    AdapterError,
    EmitResult,
    RenderContext,
    RenderResult,
    ToolRequirement,
)
from . import emit

HYPERFRAMES_VERSION = "0.7.86"
MIN_NODE_MAJOR = 22

#: Name of the video inside the project directory during a render. It is moved
#: to the artifact directory afterwards; see ``render`` for why.
STAGE_VIDEO_NAME = "colophon-render.mp4"

#: Environment HyperFrames expects. Telemetry and update checks are disabled
#: so a run cannot vary with network conditions.
_HF_ENV = {
    "HYPERFRAMES_NO_TELEMETRY": "1",
    "HYPERFRAMES_NO_UPDATE_CHECK": "1",
    "HYPERFRAMES_SKIP_SKILLS": "1",
}


class HyperFramesAdapter:
    name = "hyperframes"
    version = HYPERFRAMES_VERSION

    # -- requirements ----------------------------------------------------

    def runtime_requirements(self) -> list[ToolRequirement]:
        return [
            ToolRequirement("node", f">={MIN_NODE_MAJOR}"),
            ToolRequirement("npm", required=True),
            ToolRequirement("ffmpeg", required=True),
            ToolRequirement("ffprobe", required=True),
            ToolRequirement(f"hyperframes@{HYPERFRAMES_VERSION}", required=True),
        ]

    # -- provisioning ----------------------------------------------------

    def node_root(self, ctx: RenderContext) -> Path:
        return ctx.project_dir.parent / "runtime" / "n"

    def hyperframes_binary(self, ctx: RenderContext) -> Path:
        suffix = ".cmd" if os.name == "nt" else ""
        return self.node_root(ctx) / "node_modules" / ".bin" / f"hyperframes{suffix}"

    def provision(self, ctx: RenderContext, *, log=print) -> Path:
        """Install the pinned HyperFrames into the run's runtime directory.

        Installed per-run rather than globally so two runs on different
        renderer versions cannot interfere, and so a run directory is a
        complete, self-describing record.
        """
        binary = self.hyperframes_binary(ctx)
        if binary.exists():
            return binary

        node_root = self.node_root(ctx)
        node_root.mkdir(parents=True, exist_ok=True)
        self._materialize_package(node_root)

        npm = _tools.resolve("npm")
        log(f"  installing hyperframes@{HYPERFRAMES_VERSION} into {node_root}")
        code, out, err = run(
            [str(npm.path), "install", "--no-audit", "--no-fund", f"hyperframes@{HYPERFRAMES_VERSION}"],
            cwd=node_root,
            timeout=1800,
        )
        if code != 0 or not binary.exists():
            raise AdapterError(
                f"could not install hyperframes@{HYPERFRAMES_VERSION}:\n"
                f"{out[-2000:]}\n{err[-2000:]}"
            )
        return binary

    @staticmethod
    def _materialize_package(node_root: Path) -> Path:
        """Write the pinned ``package.json`` before installing.

        Without this, npm walks *up* looking for a package.json and happily
        installs into the nearest one it finds — which, for a run directory
        under the home folder, means dumping 138 packages into
        ``~/node_modules`` and then failing to find its own binary. The
        manifest is what pins the install to this directory.
        """
        source = Path(__file__).parent / "runtime" / "package.json"
        target = node_root / "package.json"
        if not target.is_file():
            if not source.is_file():
                raise AdapterError(f"missing bundled runtime manifest at {source}")
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        return target

    # -- emit ------------------------------------------------------------

    def emit(self, ctx: RenderContext) -> EmitResult:
        entry, fragments = emit.write_project(ctx.spec, ctx.plan, ctx.project_dir)
        files = [p.name for p in sorted(ctx.project_dir.iterdir()) if p.is_file()]

        warnings: list[str] = []
        known = {t.treatment_id for t in __import__(
            "colophon.presentation.treatments", fromlist=["TREATMENTS"]
        ).TREATMENTS.values()}
        for scene in ctx.spec.scenes:
            if scene.treatment not in known:
                warnings.append(
                    f"scene {scene.scene_id}: treatment {scene.treatment!r} "
                    f"has no dedicated stylesheet; using the plain statement layout"
                )

        return EmitResult(
            project_dir=ctx.project_dir,
            entry=entry,
            scene_fragments=fragments,
            files=files,
            warnings=warnings,
        )

    # -- render ----------------------------------------------------------

    def render(self, ctx: RenderContext, emit_result: EmitResult) -> RenderResult:
        binary = self.provision(ctx)

        ctx.out_dir.mkdir(parents=True, exist_ok=True)
        output = ctx.out_dir / "launch-video.mp4"

        # Render to a bare filename inside the project directory, then move the
        # result into place. Passing "--output ../artifact/launch-video.mp4" is
        # the most fragile part of the invocation: a tool that resolves the
        # argument against anything other than the cwd writes the video
        # somewhere unexpected, and that failure is invisible in the exit code
        # and in stderr. A bare filename has exactly one interpretation.
        staged = ctx.project_dir / STAGE_VIDEO_NAME

        argv = [
            str(binary),
            "render",
            "--fps", str(ctx.spec.canvas.fps),
            "--resolution", "landscape",
            "--strict",
            "--no-best-effort",
            "--output", staged.name,
            ".",
        ]

        env = dict(_HF_ENV)
        env["PATH"] = _tools.effective_path()

        code, out, err = run(argv, cwd=ctx.project_dir, env=env, timeout=1800)

        produced = _promote_video(staged, output)

        if code != 0 or produced is None or produced.stat().st_size <= 0:
            # A renderer can exit 0 and still write nothing, and it can fail
            # without touching stderr. Both happened here, which is why the
            # diagnostic records observed filesystem state rather than trusting
            # the process output to explain itself.
            return RenderResult(
                ok=False,
                command=argv,
                stdout=out,
                stderr=err,
                exit_code=code,
                diagnostics=_collect_diagnostics(
                    binary=binary,
                    staged=staged,
                    output=output,
                    project_dir=ctx.project_dir,
                    out_dir=ctx.out_dir,
                ),
            )

        duration_s = _probe_duration(output)
        return RenderResult(
            ok=True,
            video_path=output,
            command=argv,
            stdout=out,
            stderr=err,
            duration_s=duration_s,
            exit_code=code,
        )


def _promote_video(staged: Path, output: Path) -> Path | None:
    """Move the rendered video to its final path, or return None if absent.

    Accepts either location so that a renderer which ignored the staging name
    and wrote directly to ``output`` still succeeds. Returning None rather than
    raising is what lets the caller fold "no video" into the normal failure
    diagnostic instead of crashing with a stack trace.
    """
    if staged.is_file() and staged.stat().st_size > 0:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        shutil.move(str(staged), str(output))
        return output
    if output.is_file():
        return output
    return None


def _collect_diagnostics(
    *, binary: Path, staged: Path, output: Path, project_dir: Path, out_dir: Path
) -> dict[str, Any]:
    """Observable facts about a failed render.

    The point of listing directories is to catch the case where the renderer
    wrote the video somewhere other than ``--output`` said. Without the listing
    that failure mode is invisible: exit code, stdout and stderr all look
    normal and the only symptom is a missing file.
    """
    info: dict[str, Any] = {
        "binary": str(binary),
        "binary_exists": binary.is_file(),
        "staged": str(staged),
        "staged_exists": staged.is_file(),
        "staged_size": staged.stat().st_size if staged.is_file() else 0,
        "output": str(output),
        "output_exists": output.is_file(),
        "output_size": output.stat().st_size if output.is_file() else 0,
        "project_dir": str(project_dir),
        "out_dir": str(out_dir),
        "out_dir_exists": out_dir.is_dir(),
    }

    found: list[str] = []
    for base in (out_dir, project_dir):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.mp4")):
            found.append(f"{path} ({path.stat().st_size}B)")
    if found:
        info["mp4_found_nearby"] = "; ".join(found[:10])
    else:
        info["mp4_found_nearby"] = "none"

    try:
        info["out_dir_listing"] = ", ".join(
            sorted(p.name for p in out_dir.iterdir())
        ) or "(empty)"
    except OSError as exc:
        info["out_dir_listing"] = f"unreadable: {exc}"

    try:
        info["project_dir_listing"] = ", ".join(
            sorted(p.name for p in project_dir.iterdir())
        ) or "(empty)"
    except OSError as exc:
        info["project_dir_listing"] = f"unreadable: {exc}"

    return info


def _probe_duration(path: Path) -> float | None:
    try:
        ffprobe = _tools.resolve("ffprobe")
    except ToolError:
        return None
    code, out, _ = run(
        [
            str(ffprobe.path), "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            str(path),
        ],
        timeout=120,
    )
    if code != 0:
        return None
    try:
        return float(out.strip())
    except ValueError:
        return None
