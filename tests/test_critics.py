"""Dual-critic: review validation + merge with the deterministic verdict."""

from __future__ import annotations

import pytest

from colophon.qa.rubric import DIMENSION_NAMES, HARD_BLOCKERS
from colophon.qa.taxonomy import Assessment, Finding, Severity
from colophon.review.context import build_review_context
from colophon.review.critics import (
    ReviewError,
    VERDICT_NEEDS_VISUAL_REVIEW,
    VERDICT_PASS,
    VERDICT_REJECT,
    VERDICT_REVISE,
    merge_verdict,
    validate_review,
)


def _ctx(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v")
    frames = [tmp_path / f"frame-{i:02d}.png" for i in range(2)]
    for f in frames:
        f.write_bytes(b"f")
    sheet = tmp_path / "sheet.png"
    sheet.write_bytes(b"s")
    return build_review_context(
        attempt_id="04", spec_sha256="spec", video=video, frames=frames, contact_sheet=sheet
    )


def _clean_review(ctx, *, verdict=VERDICT_PASS, scores=None, blockers=()):
    return {
        "format_version": 1,
        "attempt_id": ctx.attempt_id,
        "review_context_sha256": ctx.review_context_sha256,
        "artifact_hashes": dict(ctx.artifact_hashes),
        "preview_hashes": dict(ctx.preview_hashes),
        "reviewed_frame_ids": sorted(ctx.preview_hashes),
        "rubric_sha256": ctx.rubric_sha256,
        "reviewer_mode": "fresh_host_vlm",
        "reviewer": "a-different-agent",
        "dimension_scores": scores if scores is not None else {n: 5 for n in DIMENSION_NAMES},
        "blockers": list(blockers),
        "verdict": verdict,
        "complete": True,
    }


def test_a_clean_pass_review_validates_and_copies_every_hash(tmp_path):
    ctx = _ctx(tmp_path)
    review = _clean_review(ctx)
    validated = validate_review(review, ctx)
    assert validated.verdict == VERDICT_PASS
    assert validated.reviewer == "a-different-agent"
    assert all(v == 5.0 for v in validated.scores.values())


def test_an_altered_context_hash_is_rejected(tmp_path):
    ctx = _ctx(tmp_path)
    review = _clean_review(ctx)
    review["review_context_sha256"] = "0" * 64
    with pytest.raises(ReviewError):
        validate_review(review, ctx)


def test_an_incomplete_frame_set_is_rejected(tmp_path):
    ctx = _ctx(tmp_path)
    review = _clean_review(ctx)
    review["reviewed_frame_ids"] = ["contact_sheet"]  # dropped the two frames
    with pytest.raises(ReviewError):
        validate_review(review, ctx)


def test_the_generator_may_not_review_itself(tmp_path):
    ctx = _ctx(tmp_path)
    review = _clean_review(ctx, scores={n: 5 for n in DIMENSION_NAMES})
    review["reviewer"] = "colophon-generator"
    with pytest.raises(ReviewError):
        validate_review(review, ctx)


def test_unknown_blocker_ids_are_rejected(tmp_path):
    ctx = _ctx(tmp_path)
    review = _clean_review(ctx, blockers=["not_a_real_blocker"])
    with pytest.raises(ReviewError):
        validate_review(review, ctx)


def test_needs_visual_review_requires_no_scores(tmp_path):
    ctx = _ctx(tmp_path)
    review = _clean_review(ctx, verdict=VERDICT_NEEDS_VISUAL_REVIEW)
    del review["dimension_scores"]
    validated = validate_review(review, ctx)
    assert validated.scores == {}
    assert validated.verdict == VERDICT_NEEDS_VISUAL_REVIEW


# --- merge_verdict ---------------------------------------------------------


def _gate_assessment(state):
    return Assessment(state, (), ())


def test_a_gate_blocker_blocks_regardless_of_a_glowing_review(tmp_path):
    ctx = _ctx(tmp_path)
    review = validate_review(_clean_review(ctx, scores={n: 5 for n in DIMENSION_NAMES}), ctx)
    gated = _gate_assessment("blocked")
    merged = merge_verdict(deterministic=gated, review=review)
    assert merged.state == "blocked"


def test_clean_gates_plus_pass_review_is_ready(tmp_path):
    ctx = _ctx(tmp_path)
    review = validate_review(_clean_review(ctx, scores={n: 5 for n in DIMENSION_NAMES}), ctx)
    merged = merge_verdict(deterministic=_gate_assessment("ready"), review=review)
    assert merged.state == "ready"
    assert merged.shippable


def test_a_review_reject_becomes_a_blocker(tmp_path):
    ctx = _ctx(tmp_path)
    review = validate_review(
        _clean_review(ctx, verdict=VERDICT_REJECT, scores={n: 2 for n in DIMENSION_NAMES}),
        ctx,
    )
    merged = merge_verdict(deterministic=_gate_assessment("ready"), review=review)
    assert merged.state == "blocked"


def test_a_rubric_blocker_becomes_a_blocker(tmp_path):
    ctx = _ctx(tmp_path)
    review = validate_review(
        _clean_review(
            ctx,
            verdict=VERDICT_PASS,
            scores={n: 5 for n in DIMENSION_NAMES},
            blockers=[HARD_BLOCKERS[0]],
        ),
        ctx,
    )
    merged = merge_verdict(deterministic=_gate_assessment("ready"), review=review)
    assert merged.state == "blocked"


def test_a_revise_review_is_ready_with_warnings(tmp_path):
    ctx = _ctx(tmp_path)
    review = validate_review(
        _clean_review(
            ctx, verdict=VERDICT_REVISE, scores={n: 3 for n in DIMENSION_NAMES}
        ),
        ctx,
    )
    merged = merge_verdict(deterministic=_gate_assessment("ready"), review=review)
    assert merged.state == "ready_with_warnings"


def test_needs_visual_review_is_ready_with_warnings(tmp_path):
    ctx = _ctx(tmp_path)
    review = validate_review(
        _clean_review(ctx, verdict=VERDICT_NEEDS_VISUAL_REVIEW), ctx
    )
    merged = merge_verdict(deterministic=_gate_assessment("ready"), review=review)
    assert merged.state == "ready_with_warnings"


def test_no_review_at_all_is_ready_with_warnings_not_ready(tmp_path):
    merged = merge_verdict(deterministic=_gate_assessment("ready"), review=None)
    assert merged.state == "ready_with_warnings"
    assert any(
        f.code == "visual_review.missing" for f in merged.warnings
    )
