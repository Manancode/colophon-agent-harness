"""Frame extraction for independent visual review.

Deliberately sealed off from the spec. This module is handed a video and a
list of timestamps and returns images — it never sees claims, treatments or
roles. A reviewer who knows which treatment a scene *intended* will rate it
more generously, so the review package is built without that context and the
spec is only joined back in when the verdict is recorded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..runtime import tools
from ..runtime.tools import ToolError, run


class ReviewError(RuntimeError):
    pass


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
    """Tile the extracted frames into one image using ffmpeg's tile filter."""
    ffmpeg = tools.resolve("ffmpeg")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not frameset.frames:
        raise ReviewError("no frames to tile")

    rows = (len(frameset.frames) + columns - 1) // columns
    inputs: list[str] = []
    for frame in frameset.frames:
        inputs += ["-i", str(frame)]

    n = len(frameset.frames)
    # ffmpeg 8.x `tile` declares a single input and tiles successive FRAMES of
    # that stream; the multi-input form ("[a][b]tile=2x1") was removed and now
    # fails with "More input link labels specified for filter 'tile' than it
    # has inputs". So concat the stills into one stream, then tile that.
    filter_complex = (
        "".join(f"[{i}:v]scale={tile_width}:-2,setsar=1[s{i}];" for i in range(n))
        + "".join(f"[s{i}]" for i in range(n))
        + f"concat=n={n}:v=1:a=0[strip];"
        + f"[strip]tile={columns}x{rows}:padding=12:color=0x0B0B0D[out]"
    )

    code, _, err = run(
        [
            str(ffmpeg.path), "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-frames:v", "1",
            "-update", "1",
            str(out_path),
        ],
        timeout=600,
    )
    if code != 0:
        # ffmpeg prints its banner first and the actual reason last, so the
        # head of stderr is always useless. Show the tail, plus the command.
        raise ReviewError(
            "contact sheet failed:\n  "
            + (err or "").strip()[-1500:]
            + f"\n  command: {' '.join(str(c) for c in [ffmpeg.path, '-y', *inputs, '-filter_complex', filter_complex])}"
        )
    frameset.contact_sheet = out_path
    return out_path


def luminance_at(video: str | Path, timestamps: Sequence[float]) -> list[float | None]:
    """Average luma at each timestamp.

    A bare canvas has a characteristic luma; a frame at or below it is blank.
    Checking every scene boundary this way is how we caught — and then
    regression-tested — the blank-frame defect at scene transitions.
    """
    ffmpeg = tools.resolve("ffmpeg")
    readings: list[float | None] = []
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
        value: float | None = None
        # `metadata=print:file=-` writes to STDOUT, not stderr. Reading only
        # stderr made every luma reading report n/a, which silently disabled
        # the blank-frame check that exists to catch empty scenes.
        for line in ((stdout or "") + "\n" + (stderr or "")).splitlines():
            if "YAVG" in line:
                try:
                    value = float(line.split("=")[-1].strip())
                except ValueError:
                    value = None
                break
        readings.append(value)
    return readings


def write_manifest(frameset: FrameSet, path: str | Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(frameset.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path
