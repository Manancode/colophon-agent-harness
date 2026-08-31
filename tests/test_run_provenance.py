"""Provenance: a verdict may only describe artifacts the spec actually made.

These pin down the defect Qodo found in ``colophon_qa``: it picked the latest
attempt without reading that attempt's manifest, then wrote the *current* spec
hash into the report. An old video would thereby carry a verdict attesting to
a spec that never produced it, which is the one claim colophon exists to be
able to make. Every test here fails against the old selection.

The rule being tested is narrower than "check the hash", and that narrowness
is the point:

* an attempt with **nothing in it** may be checked — there is no artifact to
  misattest, and "nothing to check" is the useful answer before an emit;
* an attempt with a **matching** manifest may be checked;
* an attempt that is **stale**, or that holds artifacts with **no manifest**,
  may not.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from colophon import cli
from colophon import mcp_server
from colophon.presentation.normalize import normalize
from colophon.runs import layout as run_layout
from colophon.runs import manifest as run_manifest
from colophon.spec.hash import spec_sha256
from colophon.spec.io import save
from colophon.spec.schema import VideoSpec

from .conftest import spec_dict

OLD_TITLE = "Test launch"
NEW_TITLE = "Test launch, second cut"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def normalized(**overrides) -> VideoSpec:
    """A spec in the exact form the gates will see it.

    Every hash in a run is taken *after* normalization, so a test that
    compared raw spec hashes would be comparing the wrong thing whenever
    normalization changed anything.
    """
    return normalize(VideoSpec.from_dict(spec_dict(**overrides)))[0]


def make_attempt(paths, number: int, spec: VideoSpec, *, with_video: bool = False):
    """Build an attempt the way ``colophon deliver`` would."""
    attempt = run_layout.begin_attempt(paths, number)
    (attempt.project / "index.html").write_text("<html></html>", encoding="utf-8")
    if with_video:
        (attempt.artifact / "launch-video.mp4").write_bytes(b"\x00" * 32)
    run_manifest.write_manifest(
        attempt,
        run_manifest.new_manifest(
            number, spec, renderer="test-renderer", renderer_version="1.0"
        ),
    )
    return attempt


def re_freeze(paths, spec: VideoSpec) -> None:
    """Replace a run's frozen spec in place, the way a hand edit would.

    Not the supported route any more — ``init_run`` refuses a second spec —
    but a spec file is an ordinary file on disk, and the gates have to be
    right even when someone edits one.
    """
    save(spec, paths.spec)
    paths.spec_hash.write_text(f"{spec_sha256(spec)}  spec.json\n", encoding="utf-8")


# --------------------------------------------------------------------------
# the defect
# --------------------------------------------------------------------------


def test_qa_refuses_an_attempt_emitted_from_an_older_spec(tmp_path):
    """The finding itself: no verdict may describe a video this spec didn't make."""
    old = normalized(title=OLD_TITLE)
    current = normalized(title=NEW_TITLE)
    paths = run_layout.init_run(tmp_path / "run", old)
    make_attempt(paths, 1, old)
    re_freeze(paths, current)

    with pytest.raises(run_manifest.StaleArtifactError) as caught:
        mcp_server.qa(str(paths.root))

    # Both hashes are named so the caller can see which spec moved on.
    assert spec_sha256(old)[:12] in str(caught.value)
    assert spec_sha256(current)[:12] in str(caught.value)


def test_a_refused_qa_leaves_nothing_behind(tmp_path):
    """Refusing must not look like progress.

    ``begin_attempt`` creates the directory, so a check that ran after it
    would leave an empty attempt on disk as evidence something happened — and
    a report in the stale attempt saying the current spec was checked.
    """
    old = normalized(title=OLD_TITLE)
    paths = run_layout.init_run(tmp_path / "run", old)
    make_attempt(paths, 1, old)  # the only attempt, and it is stale
    re_freeze(paths, normalized(title=NEW_TITLE))

    with pytest.raises(run_manifest.StaleArtifactError):
        mcp_server.qa(str(paths.root))

    assert not run_layout.attempt_paths(paths, 2).root.exists()
    assert not (paths.attempts / "01" / "qa" / "qa-report.json").is_file()


def test_naming_a_brand_new_attempt_starts_one(tmp_path):
    """An attempt number that does not exist yet is a request to create it.

    Not a stale artifact: there is nothing in it to misattest, and an agent
    working ahead of its first emit is doing nothing wrong.
    """
    paths = run_layout.init_run(tmp_path / "run", normalized())

    result = mcp_server.qa(str(paths.root), attempt=3)

    assert result["ok"] is True
    assert result["attempt"] == 3
    assert result["attempt_provenance"] == "empty"
    assert "emit" in result["hint"]


def test_qa_prefers_a_matching_attempt_over_a_newer_stale_one(tmp_path):
    """Latest is not the same as newest. Attempt 2 predates the current spec."""
    old = normalized(title=OLD_TITLE)
    current = normalized(title=NEW_TITLE)
    paths = run_layout.init_run(tmp_path / "run", old)
    make_attempt(paths, 1, current)  # older, but emitted from the current spec
    make_attempt(paths, 2, old)  # newer, but stale
    re_freeze(paths, current)

    result = mcp_server.qa(str(paths.root))

    assert result["ok"] is True
    assert result["attempt"] == 1
    assert result["attempt_provenance"] == "matches"


def test_qa_naming_a_stale_attempt_is_refused_too(tmp_path):
    """An explicit attempt number is a request, not an override."""
    old = normalized(title=OLD_TITLE)
    paths = run_layout.init_run(tmp_path / "run", old)
    make_attempt(paths, 1, old)
    re_freeze(paths, normalized(title=NEW_TITLE))

    with pytest.raises(run_manifest.StaleArtifactError):
        mcp_server.qa(str(paths.root), attempt=1)


def test_qa_refuses_artifacts_whose_provenance_is_unproven(tmp_path):
    """Artifacts with no manifest could have come from anywhere. Fail closed."""
    spec = normalized()
    paths = run_layout.init_run(tmp_path / "run", spec)
    attempt = run_layout.begin_attempt(paths, 1)
    (attempt.project / "index.html").write_text("<html></html>", encoding="utf-8")

    with pytest.raises(run_manifest.StaleArtifactError) as caught:
        mcp_server.qa(str(paths.root))

    assert "no manifest" in str(caught.value)


# --------------------------------------------------------------------------
# what must keep working
# --------------------------------------------------------------------------


def test_qa_still_reports_nothing_to_check_for_an_unemitted_attempt(tmp_path):
    """The whole point of 'empty': an agent asks, and is told to emit first.

    Blocking this case would have been a cheaper fix and a worse one — the
    tool exists to answer before the artifact exists, and 'nothing to check'
    is that answer.
    """
    paths = run_layout.init_run(tmp_path / "run", normalized())
    run_layout.begin_attempt(paths, 1)

    result = mcp_server.qa(str(paths.root))

    assert result["ok"] is True
    assert result["state"] == "blocked"
    assert result["attempt_provenance"] == "empty"
    assert "emit" in result["hint"]


def test_qa_refuses_a_bare_attempt_when_a_real_one_exists(tmp_path):
    """A real artifact beats an empty directory, whichever is newer."""
    spec = normalized()
    paths = run_layout.init_run(tmp_path / "run", spec)
    make_attempt(paths, 1, spec)
    run_layout.begin_attempt(paths, 2)  # newer, empty

    result = mcp_server.qa(str(paths.root))

    assert result["attempt"] == 1


# --------------------------------------------------------------------------
# one spec per run
# --------------------------------------------------------------------------


def test_init_refuses_to_freeze_a_different_spec_over_an_existing_run(tmp_path):
    """Two specs in one run is how two generations of artifacts share a hash."""
    run_dir = tmp_path / "run"
    run_layout.init_run(run_dir, normalized(title=OLD_TITLE))

    with pytest.raises(FileExistsError) as caught:
        run_layout.init_run(run_dir, normalized(title=NEW_TITLE))

    assert "new run directory" in str(caught.value)


def test_init_is_idempotent_for_the_same_spec(tmp_path):
    """Re-running init with the spec that is already there is not a conflict."""
    run_dir = tmp_path / "run"
    spec = normalized()
    run_layout.init_run(run_dir, spec)
    run_layout.init_run(run_dir, spec)

    assert json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))["title"]


def test_a_run_with_no_spec_may_still_be_initialised(tmp_path):
    paths = run_layout.init_run(tmp_path / "run", normalized())
    assert paths.spec.is_file()
    assert run_layout.frozen_spec_hash(paths) == spec_sha256(normalized())


# --------------------------------------------------------------------------
# inspecting an attempt must not create one
# --------------------------------------------------------------------------


def test_attempt_paths_does_not_create_the_attempt(tmp_path):
    paths = run_layout.init_run(tmp_path / "run", normalized())

    target = run_layout.attempt_paths(paths, 7)

    assert not target.root.exists()


# --------------------------------------------------------------------------
# the CLI shares the same rule
# --------------------------------------------------------------------------


def test_the_cli_reports_a_stale_attempt_instead_of_checking_it(tmp_path, capsys):
    """`colophon qa` and `colophon_qa` must not disagree about what is stale."""
    old = normalized(title=OLD_TITLE)
    current = normalized(title=NEW_TITLE)
    paths = run_layout.init_run(tmp_path / "run", old)
    make_attempt(paths, 1, old)
    re_freeze(paths, current)

    assert cli._evaluable_attempt(paths, current, None) is None

    error = capsys.readouterr().err
    assert "error:" in error
    assert spec_sha256(old)[:12] in error
