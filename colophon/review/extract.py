"""Frame extraction for independent visual review.

Deliberately sealed off from the spec. This module is handed a video and a
list of timestamps and returns images — it never sees claims, treatments or
roles. A reviewer who knows which treatment a scene *intended* will rate it
more generously, so the review package is built without that context and the
spec is only joined back in when the verdict is recorded.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, NamedTuple, Sequence

from ..render.contact_sheet import (
    MAX_FRAMES,
    ContactSheetError,
    build_contact_sheet as build_sheet,
)
from ..runtime import tools
from ..runtime.tools import ToolError, run

_SIGNALSTATS_RE = re.compile(r"(Y(?:MIN|LOW|AVG|HIGH|MAX))=([0-9.]+)")


class ReviewError(RuntimeError):
    pass


class LumaStats(NamedTuple):
    """Luma of one frame: its darkest, average and brightest pixel.

    All three are on ffmpeg's ``signalstats`` scale. Our encodes are
    ``yuv420p``/``color_range=tv``, so 8-bit sRGB 0-255 maps to 16-235:
    a bare #0B0B12 canvas reads 26, white text reads 235. Readings are
    therefore *not* directly comparable to a 0-255 luma formula.
    """

    ymin: float | None
    yavg: float | None
    ymax: float | None

    @property
    def spread(self) -> float | None:
        """YMAX - YMIN: how far the frame departs from a flat field.

        The blank-frame statistic, and the only one of the three that works
        regardless of whether the design is dark-on-light or light-on-dark.
        Average luma barely moves when a dark scene gains a headline (~1.6
        units, measured), and peak luma never moves at all when the content
        is *darker* than its background. Spread moves in both directions.
        """
        if self.ymin is None or self.ymax is None:
            return None
        return self.ymax - self.ymin


@dataclass
class FrameSet:
    video: Path
    frames: list[Path] = field(default_factory=list)
    contact_sheet: Path | None = None
    timestamps: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "video": str(self.video),
            "frames": [str(p) for p in self.frames],
            "contact_sheet": str(self.contact_sheet) if self.contact_sheet else None,
            "timestamps": list(self.timestamps),
        }


def scene_midpoints(plan: Any) -> list[float]:
    """One timestamp per scene, at its midpoint — away from transitions."""
    return [w.mid_s for w in plan.windows]


def extract_frames(
    video: str | Path,
    timestamps: Sequence[float],
    out_dir: str | Path,
    *,
    width: int = 1280,
    prefix: str = "frame",
) -> FrameSet:
    """Extract one PNG per timestamp.

    Seeks *before* the input (``-ss`` before ``-i``) for speed, then re-seeks
    after for accuracy on long-GOP sources.
    """
    video = Path(video)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg = tools.resolve("ffmpeg")
    frames: list[Path] = []
    stamps: list[float] = []

    for i, t in enumerate(timestamps, start=1):
        dest = out_dir / f"{prefix}-{i:02d}.png"
        code, _, err = run(
            [
                str(ffmpeg.path), "-y",
                "-ss", f"{max(0.0, t - 1.0):.3f}",
                "-i", str(video),
                "-ss", "1.000",
                "-frames:v", "1",
                "-vf", f"scale={width}:-2",
                str(dest),
            ],
            timeout=300,
        )
        if code != 0 or not dest.is_file():
            raise ReviewError(f"could not extract frame at {t}s: {err.strip()[:400]}")
        frames.append(dest)
        stamps.append(t)

    return FrameSet(video=video, frames=frames, timestamps=stamps)


def build_contact_sheet(
    frameset: FrameSet,
    out_path: str | Path,
    *,
    columns: int = 3,
    tile_width: int = 640,
) -> Path:
    """Tile the extracted frames into a 2576x1456 contact sheet.

    The ``columns`` and ``tile_width`` parameters are kept for backward
    compatibility with callers that pass them; they are ignored. The
    actual layout is decided by ``render.contact_sheet.layout_for`` so
    every review produces the same budget-sized sheet.

    If more than 12 frames were extracted, they are evenly subsampled
    before tiling -- more frames in a fixed-budget sheet becomes unreadable,
    and 12 is the most the budget can hold at the 28px patch size.
    """
    if not frameset.frames:
        raise ReviewError("no frames to tile")

    frames = frameset.frames
    if len(frames) > MAX_FRAMES:
        # Evenly spaced sample that always includes the first and last
        # frame, so a review still shows the opening and closing scenes.
        step = (len(frames) - 1) / (MAX_FRAMES - 1)
        frames = [frames[int(round(i * step))] for i in range(MAX_FRAMES)]

    try:
        result = build_sheet(frames, out_path)
    except ContactSheetError as exc:
        raise ReviewError(str(exc)) from exc

    frameset.contact_sheet = result
    return result


def luma_stats_at(video: str | Path, timestamps: Sequence[float]) -> list[LumaStats]:
    """Luma (min/average/max) of the frame at each timestamp.

    A frame showing only its background is flat: its darkest and brightest
    pixels are the same pixel, so the spread is 0 regardless of what colour
    that background is. A frame with content on it is not. Checking scene
    midpoints this way is how we caught — and then regression-tested — the
    blank-frame defect at scene transitions.
    """
    ffmpeg = tools.resolve("ffmpeg")
    readings: list[LumaStats] = []
    for t in timestamps:
        code, stdout, stderr = run(
            [
                str(ffmpeg.path), "-v", "info",
                "-ss", f"{max(0.0, t):.3f}",
                "-i", str(video),
                "-frames:v", "1",
                "-vf", "signalstats,metadata=print:file=-",
                "-f", "null", "-",
            ],
            timeout=300,
        )
        # `metadata=print:file=-` writes to STDOUT, not stderr. Reading only
        # stderr made every luma reading report n/a, which silently disabled
        # the blank-frame check that exists to catch empty scenes.
        found: dict[str, float] = {}
        for name, raw in _SIGNALSTATS_RE.findall((stdout or "") + "\n" + (stderr or "")):
            try:
                found.setdefault(name, float(raw))
            except ValueError:
                pass
        readings.append(
            LumaStats(found.get("YMIN"), found.get("YAVG"), found.get("YMAX"))
        )
    return readings


def luminance_at(video: str | Path, timestamps: Sequence[float]) -> list[float | None]:
    """Average luma at each timestamp, for logging.

    Kept because the CLI prints it, but prefer :func:`luma_stats_at` for any
    decision: the average is nearly blind to content on a dark design.
    """
    return [stats.yavg for stats in luma_stats_at(video, timestamps)]


def write_manifest(frameset: FrameSet, path: str | Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(frameset.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path
