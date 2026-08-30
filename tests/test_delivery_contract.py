"""Delivery contract: the gate that decides whether a spec is a deliverable.

Specs are built in memory on purpose. ``runs/`` is gitignored, so a test that
read from it would pass locally and fail on a fresh clone.
"""

from __future__ import annotations

from types import SimpleNamespace

from pytest import approx

from colophon.qa.stages.delivery import delivery_contract
from colophon.spec.delivery import (
    VideoDeliveryContract,
    check_delivery,
    delivery_summary,
)
from colophon.spec.schema import Canvas, Scene, VideoSpec

ROLE = "capability"
TREATMENT = "fade-rise"


def _spec(
    scene_count: int = 6,
    duration_s: float = 6.0,
    canvas: Canvas | None = None,
    scene_ids: list[str] | None = None,
) -> VideoSpec:
    ids = scene_ids if scene_ids is not None else [f"s{i}" for i in range(scene_count)]
    return VideoSpec(
        spec_id="contract-test",
        title="contract test",
        canvas=canvas or Canvas(),
        scenes=tuple(
            Scene(
                scene_id=scene_id,
                role=ROLE,
                treatment=TREATMENT,
                duration_s=duration_s,
            )
            for scene_id in ids
        ),
    )


def _plan(total_duration_s: float) -> SimpleNamespace:
    return SimpleNamespace(total_duration_s=total_duration_s)


def test_valid_spec_passes():
    assert check_delivery(_spec()) == []


def test_wrong_canvas_size_fails():
    problems = check_delivery(_spec(canvas=Canvas(width=1280, height=720)))
    assert any("canvas 1280x720" in p for p in problems)


def test_wrong_fps_fails():
    problems = check_delivery(_spec(canvas=Canvas(fps=24)))
    assert any("fps 24" in p for p in problems)


def test_total_below_floor_fails():
    problems = check_delivery(_spec(scene_count=1, duration_s=1.0))
    assert any("authored duration" in p for p in problems)


def test_total_above_ceiling_fails():
    problems = check_delivery(_spec(scene_count=40, duration_s=10.0))
    assert any("authored duration" in p for p in problems)


def test_too_many_scenes_fails():
    problems = check_delivery(_spec(scene_count=60, duration_s=1.0))
    assert any("scene count 60" in p for p in problems)


def test_duplicate_scene_ids_fails():
    spec = _spec(scene_count=3, scene_ids=["a", "a", "b"])
    problems = check_delivery(spec)
    assert any("duplicate scene_id" in p for p in problems)


def test_subsecond_scene_fails():
    problems = check_delivery(_spec(scene_count=8, duration_s=0.2))
    assert any("under the" in p for p in problems)


def test_rendered_drift_beyond_tolerance_fails():
    problems = check_delivery(_spec(), rendered_duration_s=100.0)
    assert any("drifts" in p for p in problems)


def test_small_rendered_drift_is_tolerated():
    # 36s authored vs 36.2s rendered is inside the 0.5s tolerance.
    assert check_delivery(_spec(), rendered_duration_s=36.2) == []


def test_every_violation_is_reported_not_just_the_first():
    spec = _spec(scene_count=3, duration_s=0.1, canvas=Canvas(fps=24),
                 scene_ids=["a", "a", "b"])
    problems = check_delivery(spec)
    # bad fps, short total, three tiny scenes, one duplicate id
    assert len(problems) >= 4


def test_relaxed_contract_admits_a_motion_fixture():
    # A 4s single-scene motion strip is not a deliverable and should fail the
    # default contract, but a caller gating a fixture can say so explicitly.
    fixture = _spec(scene_count=1, duration_s=4.0)
    assert check_delivery(fixture)
    relaxed = VideoDeliveryContract(min_duration_s=2.0)
    assert check_delivery(fixture, relaxed) == []


def test_gate_reports_pass_and_detail():
    result = delivery_contract(_spec(), _plan(36.0))
    assert result.passed
    assert result.stage_id == "delivery_contract"
    assert result.detail["scene_count"] == 6
    assert result.detail["timeline_duration_s"] == 36.0
    assert result.detail["baseline"] == "timeline"


def test_gate_blocks_and_is_not_advisory():
    result = delivery_contract(_spec(scene_count=1, duration_s=1.0))
    assert not result.passed
    assert result.blocking
    assert not result.advisory


# --- timeline baseline -------------------------------------------------
#
# The gate originally compared the laid-out timeline against the naive sum of
# scene durations and called the difference "drift". That is wrong: with the
# `adjacent` policy, N scenes sharing `overlap_s` at each boundary sum to more
# than the composition runs, so every match-cut video failed by construction.
# runs/cadence-01 is the real case: 6 scenes summing to 45.00s, 0.25s overlap,
# laid out to 43.6667s -- a 1.33s "drift" that was not drift at all.

CADENCE_SCENES = 6
CADENCE_AUTHORED_S = 45.0
CADENCE_TIMELINE_S = 43.666667


def _cadence_like_spec() -> VideoSpec:
    return _spec(scene_count=CADENCE_SCENES, duration_s=CADENCE_AUTHORED_S / CADENCE_SCENES)


def test_declared_overlap_is_not_reported_as_drift():
    spec = _cadence_like_spec()
    assert check_delivery(spec, timeline_duration_s=CADENCE_TIMELINE_S) == []
    problems = check_delivery(
        spec,
        timeline_duration_s=CADENCE_TIMELINE_S,
        rendered_duration_s=CADENCE_TIMELINE_S,
    )
    assert problems == []


def test_the_old_authored_baseline_would_have_failed_this_spec():
    # Pins the bug: measuring the timeline total against the authored sum
    # reports the declared overlap as drift. This is what the gate used to do.
    spec = _cadence_like_spec()
    problems = check_delivery(spec, rendered_duration_s=CADENCE_TIMELINE_S)
    assert any("drifts" in p for p in problems)
    assert any("1.33s" in p for p in problems)


def test_render_that_tracks_the_timeline_passes():
    spec = _cadence_like_spec()
    # 1310 frames at 30fps, exactly what the renderer produced.
    assert check_delivery(
        spec, timeline_duration_s=CADENCE_TIMELINE_S, rendered_duration_s=43.666667
    ) == []


def test_measured_render_drifting_from_the_timeline_fails():
    spec = _cadence_like_spec()
    problems = check_delivery(
        spec, timeline_duration_s=CADENCE_TIMELINE_S, rendered_duration_s=41.0
    )
    assert len(problems) == 1
    assert "rendered duration 41.00s drifts" in problems[0]
    assert "timeline total 43.67s" in problems[0]


def test_envelope_is_measured_on_the_timeline_total_not_the_sum():
    # 3 scenes of 2s sum to 6s but, with overlap, run for 4s. What ships is 4s,
    # so that -- not the 6s sum -- is what the floor applies to.
    spec = _spec(scene_count=3, duration_s=2.0)
    assert check_delivery(spec) == []
    problems = check_delivery(spec, timeline_duration_s=4.0)
    assert any("timeline duration 4.00s is outside" in p for p in problems)


def test_summary_reports_the_overlap_it_absorbed():
    summary = delivery_summary(_cadence_like_spec(), CADENCE_TIMELINE_S)
    assert summary["authored_duration_s"] == CADENCE_AUTHORED_S
    assert summary["timeline_duration_s"] == approx(CADENCE_TIMELINE_S, abs=1e-3)
    assert summary["overlap_s"] == approx(1.333333, abs=1e-3)


def test_gate_surfaces_measured_drift_in_detail():
    result = delivery_contract(
        _cadence_like_spec(),
        _plan(CADENCE_TIMELINE_S),
        rendered_duration_s=41.0,
    )
    assert not result.passed
    assert result.detail["rendered_duration_s"] == 41.0
    assert result.detail["timeline_duration_s"] == approx(CADENCE_TIMELINE_S, abs=1e-3)
