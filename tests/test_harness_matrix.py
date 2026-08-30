"""Harness matrix: colophon's judge must out-measure a naive "raw agent"."""

from __future__ import annotations

from colophon.bench.harness_matrix import run_matrix_demo


def test_colophon_distinguishes_good_from_broken():
    report = run_matrix_demo()
    cells = report["cells"]
    assert cells[("good_artifact", "colophon")]["passed"]
    assert not cells[("broken_stutter", "colophon")]["passed"]


def test_naive_passes_the_broken_artifact():
    # The naive baseline only checks presence, so it misses the stutter.
    report = run_matrix_demo()
    cells = report["cells"]
    assert cells[("broken_stutter", "naive")]["passed"]


def test_external_agent_rows_are_skipped_not_faked():
    report = run_matrix_demo()
    cells = report["cells"]
    for name in ("codex", "claude", "deepseek"):
        assert cells[("good_artifact", name)]["skipped"]
