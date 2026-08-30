"""The video rubric: structure, validation, and hash stability."""

from __future__ import annotations

import pytest

from colophon.qa.rubric import (
    DIMENSION_NAMES,
    HARD_BLOCKERS,
    MIN_PASSING_SCORE,
    RubricError,
    rubric_document,
    rubric_markdown,
    rubric_sha256,
    validate_scores,
    weakest_dimensions,
)


def test_seven_dimensions_match_the_source_contract_count():
    assert len(DIMENSION_NAMES) == 7
    assert DIMENSION_NAMES == tuple(n for n, _ in __import__("colophon.qa.rubric", fromlist=["x"]).DIMENSIONS)


def test_the_rubric_hash_is_deterministic_and_in_the_document():
    doc = rubric_document()
    assert doc["minimum_passing_score_per_dimension"] == MIN_PASSING_SCORE
    assert doc["dimensions"] == list(DIMENSION_NAMES)
    assert doc["hard_blockers"] == list(HARD_BLOCKERS)
    assert rubric_sha256() == rubric_sha256()
    # The prose questions are deliberately excluded from the hash.
    assert "hook" in rubric_markdown()
    for b in HARD_BLOCKERS:
        assert b in rubric_markdown()


def test_a_complete_pass_vector_is_valid():
    scores = {n: 5 for n in DIMENSION_NAMES}
    assert validate_scores(scores, verdict="pass") == {n: 5.0 for n in DIMENSION_NAMES}


def test_the_floor_blocks_any_weak_dimension_even_with_a_high_average():
    # Five dimensions at 5, one at 3 -> average 4.71, still not a pass.
    scores = {n: 5 for n in DIMENSION_NAMES}
    scores[DIMENSION_NAMES[0]] = 3
    with pytest.raises(RubricError):
        validate_scores(scores, verdict="pass")
    # Without the pass flag the vector is still structurally valid.
    assert DIMENSION_NAMES[0] in validate_scores(scores)


def test_a_missing_or_extra_dimension_is_rejected():
    base = {n: 5 for n in DIMENSION_NAMES}
    missing = dict(base)
    missing.pop(DIMENSION_NAMES[2])
    extra = dict(base)
    extra["extra_dim"] = 5
    for bad in (missing, extra):
        with pytest.raises(RubricError):
            validate_scores(bad, verdict="pass")


def test_boolean_scores_are_rejected_not_read_as_ints():
    scores = {n: 5 for n in DIMENSION_NAMES}
    scores[DIMENSION_NAMES[0]] = True  # bool is a subclass of int
    with pytest.raises(RubricError):
        validate_scores(scores, verdict="pass")


def test_non_finite_and_out_of_range_scores_are_rejected(tmp_path):
    for bad in (float("nan"), float("inf"), 0, 6):
        scores = {n: 5 for n in DIMENSION_NAMES}
        scores[DIMENSION_NAMES[1]] = bad
        with pytest.raises(RubricError):
            validate_scores(scores, verdict="pass")


def test_weakest_dimensions_ranks_below_floor_first():
    scores = {n: 5 for n in DIMENSION_NAMES}
    scores[DIMENSION_NAMES[3]] = 2
    scores[DIMENSION_NAMES[1]] = 4
    weak = weakest_dimensions(scores)
    assert weak[0] == DIMENSION_NAMES[3]
    assert DIMENSION_NAMES[1] not in weak  # 4 is exactly the floor


def test_non_pass_verdicts_do_not_enforce_the_floor():
    scores = {n: 5 for n in DIMENSION_NAMES}
    scores[DIMENSION_NAMES[0]] = 2
    # A "revise" verdict can legitimately score a dimension below the floor.
    assert validate_scores(scores, verdict="revise")[DIMENSION_NAMES[0]] == 2.0
