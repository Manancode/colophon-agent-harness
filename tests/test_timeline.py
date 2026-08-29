"""Timeline: seconds are authoritative, frames are derived, overlaps are bounded.

The overlap tests exist because of ADR 0008. Every scene boundary in the
launch document we first measured overlapped by 6-12 frames, so a
strictly-adjacent timeline was not a simplification — it was a bug.
"""

from __future__ import annotations

import pytest

from colophon.spec.schema import VideoSpec
from colophon.timeline.clock import FrameClock, cumulative_starts
from colophon.timeline.plan import build_plan, check_continuity

from .conftest import FPS, scene, spec_dict


class TestFrameClock:
    def test_rejects_non_positive_fps(self):
        with pytest.raises(ValueError):
            FrameClock(0)

    def test_whole_seconds_map_exactly(self):
        clock = FrameClock(FPS)
        assert clock.to_frames(1.0) == 30
        assert clock.to_frames(2.0) == 60

    def test_rounds_half_up_at_the_half_frame(self):
        # 1/60 s at 30fps is exactly half a frame; half-up means 1, not 0.
        assert FrameClock(FPS).to_frames(1 / 60) == 1

    def test_round_trip_is_stable(self):
        clock = FrameClock(FPS)
        for seconds in (0.25, 0.5, 1.0, 1.75, 7.3):
            assert clock.to_seconds(clock.to_frames(seconds)) == pytest.approx(
                clock.snap(seconds)
            )

    def test_timecode_format(self):
        assert FrameClock(FPS).timecode(1830) == "00:01:01.000"


class TestCumulativeStarts:
    def test_starts_are_cumulative_not_rounded_per_scene(self):
        # 1/60 s is half a frame at 30fps. Rounding each duration independently
        # would give 1 + 1 = 2 frames for the second start; accumulating the
        # seconds first gives round(1.0 frames) = 1. Rounding must not compound.
        assert cumulative_starts([1 / 60, 1 / 60], FPS) == [0, 1]

    def test_first_start_is_zero_and_monotonic(self):
        starts = cumulative_starts([0.3, 0.3, 0.3], FPS)
        assert starts[0] == 0
        assert starts == sorted(starts)


def _spec_with(**overrides):
    return VideoSpec.from_dict(spec_dict(**overrides))


class TestBuildPlan:
    def test_adjacent_without_overlap_is_butt_joined(self):
        spec = _spec_with(
            scenes=[scene("a", duration_s=2.0), scene("b", duration_s=2.0)],
            timeline={"policy": "adjacent", "overlap_s": 0.0, "transition": "cut", "transition_ms": 0},
        )
        plan = build_plan(spec)
        starts = [w.start_frame for w in plan.windows]
        assert starts == [0, 60]
        assert plan.total_frames == 120

    def test_overlap_pulls_each_scene_earlier(self):
        # 0.2s at 30fps is 6 frames.
        spec = _spec_with(
            scenes=[scene("a", duration_s=2.0), scene("b", duration_s=2.0)],
            timeline={"policy": "adjacent", "overlap_s": 0.2, "transition": "match_cut", "transition_ms": 400},
        )
        plan = build_plan(spec)
        starts = [w.start_frame for w in plan.windows]
        assert starts == [0, 54]
        # the video is shorter than the sum of its parts
        assert plan.total_frames == 114 < 120

    def test_overlap_can_never_swallow_a_scene(self):
        # Two very short scenes with an overlap far larger than either. The
        # clamp must keep both scenes visible.
        spec = _spec_with(
            scenes=[scene("a", duration_s=0.05), scene("b", duration_s=0.05)],
            timeline={"policy": "adjacent", "overlap_s": 5.0, "transition": "match_cut", "transition_ms": 400},
        )
        plan = build_plan(spec)
        starts = [w.start_frame for w in plan.windows]
        assert starts[1] < plan.windows[0].end_frame
        assert starts[1] > 0

    def test_negative_overlap_is_treated_as_zero(self):
        spec = _spec_with(
            scenes=[scene("a"), scene("b")],
            timeline={"policy": "adjacent", "overlap_s": -3.0, "transition": "cut", "transition_ms": 0},
        )
        plan = build_plan(spec)
        assert [w.start_frame for w in plan.windows] == [0, 60]

    def test_explicit_policy_is_not_supported_in_v0(self):
        spec = _spec_with(
            timeline={"policy": "explicit", "overlap_s": 0.0, "transition": "cut", "transition_ms": 0}
        )
        with pytest.raises(NotImplementedError):
            build_plan(spec)


class TestCheckContinuity:
    def test_gap_is_always_a_bug(self):
        spec = _spec_with(
            scenes=[scene("a", duration_s=2.0), scene("b", duration_s=2.0)],
            timeline={"policy": "adjacent", "overlap_s": 0.0, "transition": "cut", "transition_ms": 0},
        )
        plan = build_plan(spec)
        # force a gap
        object.__setattr__(plan.windows[1], "start_frame", 90)
        problems = check_continuity(plan, max_overlap_frames=0)
        assert any("gap" in p for p in problems)

    def test_declared_overlap_is_legal(self):
        spec = _spec_with(
            scenes=[scene("a", duration_s=2.0), scene("b", duration_s=2.0)],
            timeline={"policy": "adjacent", "overlap_s": 0.2, "transition": "match_cut", "transition_ms": 400},
        )
        plan = build_plan(spec)
        assert check_continuity(plan, max_overlap_frames=6) == []

    def test_overlap_beyond_the_declared_maximum_is_reported(self):
        spec = _spec_with(
            scenes=[scene("a", duration_s=2.0), scene("b", duration_s=2.0)],
            timeline={"policy": "adjacent", "overlap_s": 0.2, "transition": "match_cut", "transition_ms": 400},
        )
        plan = build_plan(spec)
        assert check_continuity(plan, max_overlap_frames=0)
