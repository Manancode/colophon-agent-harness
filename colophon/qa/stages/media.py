"""Media contract — checks the rendered MP4 against the spec.

Runs after render. The point is to catch the class of defect where the render
"succeeded" but produced something that is not the video the spec describes.
"""

from __future__ import annotations

import json
from typing import Any

from ...runtime import tools
from ...runtime.tools import ToolError, run
from ...spec.schema import VideoSpec
from ...timeline.plan import TimelinePlan
from ..runner import StageResult

#: How far the rendered duration may drift from the planned one. A second is
#: generous for container muxing; anything more means scenes were dropped,
#: duplicated, or the fps disagreed with the spec.
DURATION_TOLERANCE_S = 1.0


def media_contract(
    spec: VideoSpec,
    plan: TimelinePlan,
    *,
    video_path: Any = None,
    **_: Any,
) -> StageResult:
    if video_path is None:
        return StageResult(
            stage_id="media_contract",
            passed=False,
            problems=["no video; run render first"],
        )
    video_path = _coerce_path(video_path)
    if not video_path.is_file() or video_path.stat().st_size <= 0:
        return StageResult(
            stage_id="media_contract",
            passed=False,
            problems=[f"{video_path} is missing or empty"],
        )

    try:
        ffprobe = tools.resolve("ffprobe")
    except ToolError as exc:
        return StageResult(
            stage_id="media_contract", passed=False, problems=[str(exc)]
        )

    code, out, err = run(
        [
            str(ffprobe.path), "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate",
            "-of", "json",
            str(video_path),
        ],
        timeout=180,
    )
    if code != 0:
        return StageResult(
            stage_id="media_contract",
            passed=False,
            problems=[f"ffprobe failed: {err.strip()[:400]}"],
        )

    try:
        probe = json.loads(out)
    except json.JSONDecodeError as exc:
        return StageResult(
            stage_id="media_contract",
            passed=False,
            problems=[f"could not parse ffprobe output: {exc}"],
        )

    problems: list[str] = []
    streams = probe.get("streams") or []
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    if not video_streams:
        problems.append("no video stream in the output")

    if video_streams:
        vs = video_streams[0]
        width, height = vs.get("width"), vs.get("height")
        if width != spec.canvas.width or height != spec.canvas.height:
            problems.append(
                f"resolution {width}x{height} != spec "
                f"{spec.canvas.width}x{spec.canvas.height}"
            )
        rate = vs.get("r_frame_rate") or ""
        if "/" in rate:
            num, _, den = rate.partition("/")
            try:
                fps = round(int(num) / int(den), 3)
            except (ValueError, ZeroDivisionError):
                fps = None
            if fps is not None and abs(fps - spec.canvas.fps) > 0.05:
                problems.append(f"frame rate {fps} != spec fps {spec.canvas.fps}")

    try:
        duration = float((probe.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0

    expected = plan.total_duration_s
    if duration and abs(duration - expected) > DURATION_TOLERANCE_S:
        problems.append(
            f"duration {duration:.2f}s differs from planned {expected:.2f}s "
            f"by more than {DURATION_TOLERANCE_S}s"
        )

    detail = {
        "duration_s": duration,
        "planned_duration_s": expected,
        "video_streams": len(video_streams),
        "audio_streams": len(audio_streams),
        "bytes": video_path.stat().st_size,
    }

    return StageResult(
        stage_id="media_contract",
        passed=not problems,
        problems=problems,
        detail=detail,
    )


def _coerce_path(value: Any):
    from pathlib import Path

    return value if isinstance(value, Path) else Path(str(value))
