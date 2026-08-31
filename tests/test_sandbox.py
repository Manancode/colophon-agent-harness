"""The MCP server may only touch paths inside the root it was given.

Colophon's writing tools carry no annotation, on purpose, so an agent is not
interrupted by an approval prompt mid-loop. The consequence is that nothing
asks a human before a write happens — which makes the path check the only
thing standing between a client and the rest of the filesystem. These tests
are what makes that check trustworthy.

The root is global, so every test here resets it. Leaking a configured root
into another test file would make that file's temporary directories look like
escapes, and the failure would point at the wrong module entirely.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from colophon import mcp_server
from colophon import sandbox

from .conftest import spec_dict


@pytest.fixture(autouse=True)
def no_root():
    sandbox.reset()
    yield
    sandbox.reset()


def write_spec(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec_dict()), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# the check itself
# --------------------------------------------------------------------------


def test_a_path_inside_the_root_is_allowed(tmp_path):
    sandbox.configure(tmp_path)
    assert sandbox.within(tmp_path / "run") == (tmp_path / "run").resolve()


def test_the_root_itself_is_allowed(tmp_path):
    sandbox.configure(tmp_path)
    assert sandbox.within(tmp_path) == tmp_path.resolve()


def test_a_path_outside_the_root_is_refused(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    sandbox.configure(root)

    with pytest.raises(sandbox.PathEscapeError) as caught:
        sandbox.within(tmp_path / "elsewhere")

    assert "outside the server root" in str(caught.value)
    assert sandbox.ROOT_ENV in str(caught.value)


def test_a_sibling_sharing_the_root_prefix_is_refused(tmp_path):
    """`startswith` would have passed this. `is_relative_to` does not."""
    sandbox.configure(tmp_path / "work")

    with pytest.raises(sandbox.PathEscapeError):
        sandbox.within(tmp_path / "workspace")


def test_a_symlink_pointing_out_of_the_root_is_refused(tmp_path):
    """Resolved before the check, so a link out is not a way out."""
    root = tmp_path / "root"
    (root / "inside").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "target").mkdir()
    (root / "inside" / "link").symlink_to(outside / "target")
    sandbox.configure(root)

    with pytest.raises(sandbox.PathEscapeError):
        sandbox.within(root / "inside" / "link")


def test_with_no_root_configured_the_library_is_unconstrained(tmp_path):
    """Used as a library there is no deputy, so there is nothing to confine."""
    assert sandbox.root() is None
    assert sandbox.within(tmp_path / "anywhere") == (tmp_path / "anywhere").resolve()


def test_an_optional_path_may_be_none(tmp_path):
    sandbox.configure(tmp_path)
    assert sandbox.within_optional(None) is None


# --------------------------------------------------------------------------
# configuring it
# --------------------------------------------------------------------------


def test_the_environment_variable_sets_the_root(tmp_path, monkeypatch):
    monkeypatch.setenv(sandbox.ROOT_ENV, str(tmp_path))
    assert sandbox.configure() == tmp_path.resolve()


def test_an_explicit_root_beats_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(sandbox.ROOT_ENV, str(tmp_path / "from-env"))
    chosen = tmp_path / "from-flag"
    chosen.mkdir()

    assert sandbox.configure(chosen) == chosen.resolve()


def test_an_explicit_root_defaults_to_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.delenv(sandbox.ROOT_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    assert sandbox.configure() == tmp_path.resolve()


def test_a_tilde_in_the_root_is_expanded(tmp_path, monkeypatch):
    """`COLOPHON_ROOT=~/runs` is the natural thing to write in a shell profile.

    Only ``~`` is expanded, never ``$VARS``: a directory with a literal ``$``
    in its name is unusual but legal, and a path check that quietly rewrote
    what it was given is a path check that cannot be reasoned about.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    sandbox.configure("~/work")

    assert sandbox.root() == (tmp_path / "work").resolve()


# --------------------------------------------------------------------------
# the tools honour it
# --------------------------------------------------------------------------


def test_init_run_refuses_a_run_directory_outside_the_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    spec_path = write_spec(root / "spec.json")
    escape = tmp_path / "elsewhere" / "run"
    sandbox.configure(root)

    with pytest.raises(sandbox.PathEscapeError):
        mcp_server.init_run(str(spec_path), str(escape))

    # A refused write must not leave a run behind as evidence it happened.
    assert not escape.exists()


def test_init_run_refuses_a_spec_outside_the_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    spec_path = write_spec(tmp_path / "spec.json")
    sandbox.configure(root)

    with pytest.raises(sandbox.PathEscapeError):
        mcp_server.init_run(str(spec_path), str(root / "run"))


def test_init_run_accepts_paths_inside_the_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    spec_path = write_spec(root / "spec.json")
    sandbox.configure(root)

    result = mcp_server.init_run(str(spec_path), str(root / "run"))

    assert result["ok"] is True
    assert (root / "run" / "spec.json").is_file()


def test_qa_refuses_a_run_directory_outside_the_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    sandbox.configure(root)

    with pytest.raises(sandbox.PathEscapeError):
        mcp_server.qa(str(tmp_path / "elsewhere" / "run"))


def test_plan_refuses_a_run_directory_outside_the_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    sandbox.configure(root)

    with pytest.raises(sandbox.PathEscapeError):
        mcp_server.plan(str(tmp_path / "elsewhere" / "run"))


def test_validate_refuses_a_run_directory_outside_the_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    sandbox.configure(root)

    with pytest.raises(sandbox.PathEscapeError):
        mcp_server.validate(str(tmp_path / "elsewhere" / "run"))


def test_design_refuses_an_outside_working_directory(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    spec_path = write_spec(root / "spec.json")
    sandbox.configure(root)

    with pytest.raises(sandbox.PathEscapeError):
        mcp_server.design(str(spec_path), out_dir=str(tmp_path / "escape"))


def test_design_refuses_an_outside_workspace(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    spec_path = write_spec(root / "spec.json")
    sandbox.configure(root)

    with pytest.raises(sandbox.PathEscapeError):
        mcp_server.design(str(spec_path), workspace=str(tmp_path / "escape"))


# --------------------------------------------------------------------------
# the server configures it before running
# --------------------------------------------------------------------------


def test_serve_configures_the_root_before_serving(tmp_path, monkeypatch):
    """A server that forgot to call configure() would be wide open."""
    calls: dict[str, object] = {}

    class _FakeServer:
        def run(self, **kwargs):
            calls.update(kwargs)

    monkeypatch.setattr(mcp_server, "build_server", lambda token=None: _FakeServer())

    mcp_server.serve(root=tmp_path)

    assert sandbox.root() == tmp_path.resolve()
    assert calls["host"] == mcp_server.DEFAULT_HOST


def test_serve_defaults_the_root_to_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.delenv(sandbox.ROOT_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        mcp_server,
        "build_server",
        lambda token=None: type("S", (), {"run": lambda self, **k: None})(),
    )

    mcp_server.serve()

    assert sandbox.root() == tmp_path.resolve()
