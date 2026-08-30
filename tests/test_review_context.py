"""Hash-bound review context: binding, symlink refusal, tamper detection."""

from __future__ import annotations

import os

import pytest

from colophon.qa.rubric import rubric_sha256
from colophon.review.context import (
    ContextError,
    build_review_context,
    read_review_context,
    validate_context,
    write_review_context,
)


def _files(tmp_path, n_frames=3, video_bytes=b"v", frame_bytes=b"f"):
    video = tmp_path / "video.mp4"
    video.write_bytes(video_bytes)
    frames = []
    for i in range(n_frames):
        p = tmp_path / f"frame-{i:02d}.png"
        p.write_bytes(frame_bytes)
        frames.append(p)
    sheet = tmp_path / "sheet.png"
    sheet.write_bytes(b"s")
    return video, frames, sheet


def _ctx(tmp_path):
    video, frames, sheet = _files(tmp_path)
    return build_review_context(
        attempt_id="04",
        spec_sha256="spec123",
        video=video,
        frames=frames,
        contact_sheet=sheet,
    )


def test_the_context_binds_every_preview_and_artifact(tmp_path):
    ctx = _ctx(tmp_path)
    assert ctx.attempt_id == "04"
    assert ctx.spec_sha256 == "spec123"
    assert ctx.rubric_sha256 == rubric_sha256()
    assert sorted(ctx.preview_ids) == ["contact_sheet", "frame_01", "frame_02", "frame_03"]
    assert set(ctx.preview_hashes) == set(ctx.preview_ids)
    assert "video" in ctx.artifact_hashes


def test_the_context_digest_is_stable_for_the_same_inputs(tmp_path):
    a = _ctx(tmp_path)
    b = _ctx(tmp_path)
    assert a.review_context_sha256 == b.review_context_sha256
    assert len(a.review_context_sha256) == 64


def test_reviewed_frame_ids_must_be_the_complete_sorted_set(tmp_path):
    ctx = _ctx(tmp_path)
    assert ctx.preview_ids == sorted(ctx.preview_hashes)


def test_symlinks_and_missing_files_are_refused(tmp_path):
    good = tmp_path / "good.mp4"
    good.write_bytes(b"x")
    link = tmp_path / "link.mp4"
    os.symlink(good, link)
    with pytest.raises(ContextError):
        build_review_context(
            attempt_id="04", spec_sha256="s", video=link, frames=[], contact_sheet=None
        )
    missing = tmp_path / "absent.mp4"
    with pytest.raises(ContextError):
        build_review_context(
            attempt_id="04", spec_sha256="s", video=missing, frames=[], contact_sheet=None
        )


def test_context_round_trips_through_disk(tmp_path):
    ctx = _ctx(tmp_path)
    path = write_review_context(ctx, tmp_path / "review-context.json")
    back = read_review_context(path)
    assert back == ctx
    validate_context(back)  # does not raise


def test_a_changed_rubric_invalidates_the_context(tmp_path):
    ctx = _ctx(tmp_path)
    with pytest.raises(ContextError):
        validate_context(ctx, expected_rubric="0" * 64)


def test_a_tampered_context_fails_its_own_digest(tmp_path):
    import dataclasses

    ctx = _ctx(tmp_path)
    # Manually rewriting one preview hash without updating the digest.
    tampered = dataclasses.replace(
        ctx,
        preview_hashes={**ctx.preview_hashes, "contact_sheet": "deadbeef"},
    )
    # The stored digest no longer matches the contents.
    assert tampered.to_dict()["review_context_sha256"] == ctx.review_context_sha256
    with pytest.raises(ContextError):
        validate_context(tampered)
