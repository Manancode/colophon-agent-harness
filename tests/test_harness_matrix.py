"""Harness matrix: colophon's judge must out-measure a naive "raw agent"."""

from __future__ import annotations

import pytest

from colophon.bench.harness_matrix import (
    ExternalAgentHarness,
    colophon_harness,
    run_matrix_demo,
)
from colophon.runtime.tools import EXTRA_PATH_DIRS, effective_path


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


# -- the regression that motivated this file ---------------------------------
# These three external CLIs are installed on plenty of dev machines (Homebrew
# /usr/local). The matrix used to raise NotImplementedError the moment one was
# found, taking every other row down with it, and only "passed" in CI because
# the sandbox PATH hid them. Discovery must not depend on the ambient PATH,
# and an unwired harness must skip rather than crash.


def test_an_installed_but_unwired_agent_skips_instead_of_raising(monkeypatch):
    harness = ExternalAgentHarness("codex", "codex")
    monkeypatch.setattr(harness, "_locate", lambda: "/opt/homebrew/bin/codex")

    result = harness("<section id='s1'></section>", brief="good_artifact")

    assert result.skipped
    assert not result.passed
    assert "not wired" in result.detail


def test_a_missing_binary_is_reported_as_missing(monkeypatch):
    harness = ExternalAgentHarness("deepseek", "dsh")
    monkeypatch.setattr(harness, "_locate", lambda: None)

    result = harness("<section id='s1'></section>", brief="good_artifact")

    assert result.skipped
    assert "not found" in result.detail


def test_discovery_uses_the_effective_path_not_the_ambient_one(monkeypatch, tmp_path):
    """Discovery must be reproducible regardless of how stripped PATH is.

    The fake binary lives only in the *effective* prefix, and the ambient PATH
    is emptied. A bare ``shutil.which`` would find nothing, so finding it
    proves the effective PATH was consulted.
    """
    import colophon.bench.harness_matrix as hm

    bindir = tmp_path / "brew"
    bindir.mkdir()
    fake = bindir / "codex"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)

    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(hm, "effective_path", lambda: str(bindir))

    assert ExternalAgentHarness("codex", "codex")._locate() == str(fake)


def test_the_effective_path_restores_homebrew_when_the_sandbox_strips_it(monkeypatch):
    """The reason discovery broke: sandboxes drop /opt/homebrew/bin."""
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert any(d in effective_path() for d in EXTRA_PATH_DIRS)


def test_the_matrix_survives_every_agent_being_installed(monkeypatch):
    """One installed CLI must not take the whole benchmark down."""
    monkeypatch.setattr(
        ExternalAgentHarness, "_locate", lambda self: f"/usr/bin/{self.binary}"
    )

    report = run_matrix_demo()
    cells = report["cells"]

    # colophon and naive still measured normally...
    assert cells[("good_artifact", "colophon")]["passed"]
    assert not cells[("broken_stutter", "colophon")]["passed"]
    # ...and the external rows are SKIP, never a crash and never a fake pass.
    for name in ("codex", "claude", "deepseek"):
        assert cells[("good_artifact", name)]["skipped"]


def test_the_integration_point_is_still_clearly_marked():
    with pytest.raises(NotImplementedError):
        ExternalAgentHarness("codex", "codex")._invoke("some brief")


def test_colophon_harness_carries_its_name():
    assert colophon_harness.name == "colophon"
