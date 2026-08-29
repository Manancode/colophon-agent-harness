"""The frame clock. The only place seconds become frames.

Why this module exists: storing ``startFrame`` values directly means that when
a composition switches from 30 to 60 fps, every hand-tuned frame constant
silently means something else.
In Colophon, seconds are authoritative and frames are *derived* — always by
going through this class.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrameClock:
    """Converts between seconds and integer frames at a fixed fps."""

    fps: int

    def __post_init__(self) -> None:
        if self.fps <= 0:
            raise ValueError(f"fps must be positive, got {self.fps}")

    def to_frames(self, seconds: float) -> int:
        """Frames for a duration, rounded half-up to the nearest frame."""
        return int(seconds * self.fps + 0.5)

    def to_seconds(self, frames: int) -> float:
        return frames / self.fps

    def snap(self, seconds: float) -> float:
        """Snap a second value onto the frame grid."""
        return self.to_frames(seconds) / self.fps

    def timecode(self, frames: int) -> str:
        total_s = frames / self.fps
        mm, ss = divmod(total_s, 60)
        hh, mm = divmod(int(mm), 60)
        return f"{hh:02d}:{mm:02d}:{ss:06.3f}"


def cumulative_starts(durations_s: list[float], fps: int) -> list[int]:
    """Frame index where each scene begins, for an ``adjacent`` timeline.

    Each boundary is rounded from the *cumulative* second total rather than
    accumulated frame-by-frame, so rounding never compounds. Guarantees:
      - starts are non-decreasing
      - starts[0] == 0
      - total frames == round(sum(durations) * fps)
    """
    starts: list[int] = []
    acc = 0.0
    for d in durations_s:
        starts.append(int(acc * fps + 0.5))
        acc += d
    return starts
