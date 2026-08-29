"""Layout scenes onto the clock.

Produces the immutable ``SceneWindow`` list that every downstream stage
(render, QA, review, repair) reads. Nothing recomputes timing for itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..spec.schema import VideoSpec
from .clock import FrameClock


@dataclass(frozen=True)
class SceneWindow:
    """Where a scene sits on the clock, in both units."""

    scene_id: str
    index: int
    start_s: float
    end_s: float
    duration_s: float
    start_frame: int
    end_frame: int
    duration_frames: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "index": self.index,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "duration_s": self.duration_s,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "duration_frames": self.duration_frames,
        }

    @property
    def mid_s(self) -> float:
        return (self.start_s + self.end_s) / 2.0


@dataclass(frozen=True)
class TimelinePlan:
    spec_id: str
    fps: int
    total_frames: int
    total_duration_s: float
    windows: tuple[SceneWindow, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "fps": self.fps,
            "total_frames": self.total_frames,
            "total_duration_s": self.total_duration_s,
            "scenes": [w.to_dict() for w in self.windows],
        }

    def window(self, scene_id: str) -> SceneWindow | None:
        return next((w for w in self.windows if w.scene_id == scene_id), None)

    def window_at(self, seconds: float) -> SceneWindow | None:
        for w in self.windows:
            if w.start_s <= seconds < w.end_s:
                return w
        return self.windows[-1] if self.windows else None


def build_plan(spec: VideoSpec) -> TimelinePlan:
    """Lay out the spec's scenes according to its timeline policy.

    Consecutive scenes overlap by ``timeline.overlap_s`` (clamped so no scene
    can be swallowed by its neighbour). With ``overlap_s = 0`` this reduces
    exactly to a butt-joined timeline.
    """
    if spec.timeline.policy == "explicit":
        raise NotImplementedError("timeline.policy 'explicit' is not supported in V0")

    clock = FrameClock(spec.canvas.fps)
    durations = [clock.to_frames(s.duration_s) for s in spec.scenes]
    overlap = clock.to_frames(max(0.0, spec.timeline.overlap_s))

    starts: list[int] = []
    for i, dur in enumerate(durations):
        if i == 0:
            starts.append(0)
            continue
        # never let the overlap consume a whole scene
        allowed = min(overlap, durations[i - 1] - 1, dur - 1)
        allowed = max(0, allowed)
        starts.append(starts[i - 1] + durations[i - 1] - allowed)

    windows: list[SceneWindow] = []
    for i, (scene, start_frame) in enumerate(zip(spec.scenes, starts)):
        duration_frames = durations[i]
        windows.append(
            SceneWindow(
                scene_id=scene.scene_id,
                index=i,
                start_s=round(start_frame / clock.fps, 6),
                end_s=round((start_frame + duration_frames) / clock.fps, 6),
                duration_s=scene.duration_s,
                start_frame=start_frame,
                end_frame=start_frame + duration_frames,
                duration_frames=duration_frames,
            )
        )

    total_frames = max((w.end_frame for w in windows), default=0)
    return TimelinePlan(
        spec_id=spec.spec_id,
        fps=clock.fps,
        total_frames=total_frames,
        total_duration_s=round(total_frames / clock.fps, 6),
        windows=tuple(windows),
    )


def check_continuity(plan: TimelinePlan, max_overlap_frames: int = 0) -> list[str]:
    """Structural checks on the layout.

    Overlaps up to ``max_overlap_frames`` are legal — that is the match-cut
    window. Anything beyond it, or any gap at all, is a bug.
    """
    problems: list[str] = []
    windows = plan.windows

    if not windows:
        return ["timeline has no scenes"]

    if windows[0].start_frame != 0:
        problems.append(f"first scene starts at frame {windows[0].start_frame}, expected 0")

    for prev, cur in zip(windows, windows[1:]):
        delta = cur.start_frame - prev.end_frame
        if delta > 0:
            problems.append(
                f"gap of {delta} frame(s) between {prev.scene_id} and {cur.scene_id}"
            )
        elif -delta > max_overlap_frames:
            problems.append(
                f"overlap of {-delta} frame(s) between {prev.scene_id} and "
                f"{cur.scene_id} exceeds the declared maximum of {max_overlap_frames}"
            )

    for w in windows:
        if w.duration_frames <= 0:
            problems.append(f"scene {w.scene_id} has non-positive duration")
        if w.end_frame > plan.total_frames:
            problems.append(
                f"scene {w.scene_id} ends at {w.end_frame} "
                f"past total {plan.total_frames}"
            )

    return problems
