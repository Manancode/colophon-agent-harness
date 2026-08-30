"""Phase 7: real agent invocation, and the opt-in gate around it.

The rule for this file: **no test may ever run a real agent.** Every binary is
a shell script in ``tmp_path``. That is not paranoia — while wiring this up, a
leftover test that asserted ``NotImplementedError`` turned into a genuine 106
second codex call inside the suite, because the moment ``_invoke`` became real
the old assertion stopped protecting anything.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from colophon.bench import agents
from colophon.bench import harness_matrix as hm
from colophon.bench.agents import (
    ClaudeProfile,
    CodexProfile,
    GenericProfile,
    collect_document,
    invoke_agent,
    profile_for,
    run_agent_for_brief,
)
from colophon.cli import main


# -- fake agents ------------------------------------------------------------

GOOD_HTML = """<!doctype html><html><head><style>
@keyframes w{from{transform:translateY(16px)}to{transform:none}}
.m-word-sweep .word{display:inline-block;animation-name:w;
  animation-timing-function:cubic-bezier(.2,.75,.34,.94)}
h1{font-family:sans-serif;font-weight:700}
@media (prefers-reduced-motion: reduce){.m-word-sweep .word{animation:none}}
</style></head><body>
<div data-composition-id="c1" style="background:#0B0B0D">
  <section id="s1" class="clip" style="background:#0B0B0D">
    <h1 data-motion="word-sweep"><span class="word"
      style="animation-delay:0ms;animation-duration:480ms">Ship</span></h1>
  </section>
</div></body></html>
"""


def _write_agent(directory: Path, name: str, body: str) -> Path:
    """Drop an executable shell script named ``name`` into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _good_agent(directory: Path, name: str = "codex") -> Path:
    return _write_agent(
        directory,
        name,
        f"#!/bin/sh\ncat > index.html <<'HTML'\n{GOOD_HTML}\nHTML\necho wrote\n",
    )


@pytest.fixture
def fake_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A bin dir holding a fake ``codex`` that writes a passing artifact."""
    bindir = tmp_path / "bin"
    _good_agent(bindir, "codex")
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    return bindir


# -- argv shape (guards against CLI flag drift) ----------------------------


def test_codex_uses_the_non_interactive_subcommand():
    argv = CodexProfile().build_argv("P", Path("/tmp/x"))
    assert argv[:2] == ["codex", "exec"]


def test_codex_writes_only_inside_its_workspace():
    argv = CodexProfile().build_argv("P", Path("/tmp/x"))
    assert "workspace-write" in argv
    # The dangerous alternatives must not be the default.
    assert "danger-full-access" not in argv
    assert "dangerously-bypass-approvals-and-sandbox" not in argv


def test_codex_does_not_pollute_the_users_session_history():
    argv = CodexProfile().build_argv("P", Path("/tmp/x"))
    assert "--ephemeral" in argv


def test_codex_starts_outside_a_git_repo():
    argv = CodexProfile().build_argv("P", Path("/tmp/x"))
    assert "--skip-git-repo-check" in argv


def test_claude_uses_print_mode_and_narrow_permissions():
    argv = ClaudeProfile().build_argv("P", Path("/tmp/x"))
    assert argv[:2] == ["claude", "-p"]
    assert "--permission-mode" in argv
    assert "acceptEdits" in argv
    # bypassPermissions would let it do far more than write a file.
    assert "bypassPermissions" not in argv


def test_the_prompt_is_the_final_argument_for_every_profile():
    for profile in (CodexProfile(), ClaudeProfile(), GenericProfile("dsh", "dsh")):
        assert profile.build_argv("THE PROMPT", Path("/tmp/x"))[-1] == "THE PROMPT"


def test_unknown_agents_fall_back_to_a_generic_profile():
    assert isinstance(profile_for("codex"), CodexProfile)
    assert isinstance(profile_for("zed"), GenericProfile)


def test_generic_profile_honours_prefix_args():
    argv = GenericProfile("dsh", "dsh", ("--quiet",)).build_argv("P", Path("/tmp/x"))
    assert argv == ["dsh", "--quiet", "P"]


# -- document collection ----------------------------------------------------


def test_collect_document_prefers_index_html(tmp_path: Path):
    (tmp_path / "index.html").write_text("<html>real</html>")
    (tmp_path / "notes.html").write_text("<html>notes</html>" * 100)
    assert collect_document(tmp_path).name == "index.html"


def test_collect_document_falls_back_to_the_largest_html(tmp_path: Path):
    """An agent that names its file something else is still measured."""
    (tmp_path / "draft.html").write_text("<html>short</html>")
    (tmp_path / "scene.html").write_text("<html>the real artifact</html>" * 50)
    assert collect_document(tmp_path).name == "scene.html"


def test_collect_document_ignores_empty_files(tmp_path: Path):
    (tmp_path / "index.html").write_text("")
    assert collect_document(tmp_path) is None


def test_collect_document_returns_none_for_an_empty_tree(tmp_path: Path):
    assert collect_document(tmp_path) is None


def test_collect_document_is_deterministic_on_equal_sizes(tmp_path: Path):
    for name in ("b.html", "a.html", "c.html"):
        (tmp_path / name).write_text("x" * 50)
    picks = {collect_document(tmp_path).name for _ in range(5)}
    assert len(picks) == 1


# -- invocation outcomes ----------------------------------------------------


def test_a_missing_binary_is_reported_not_raised():
    invocation = invoke_agent(GenericProfile("ghost", "ghost-agent-xyz"), "hi")
    assert not invocation.produced_document
    assert "not found" in invocation.error


def test_a_successful_run_captures_the_document_and_the_argv(fake_bin: Path):
    invocation = invoke_agent(CodexProfile(), "make a scene", timeout_s=30)
    assert invocation.produced_document
    assert invocation.exit_code == 0
    assert invocation.document_path.endswith("index.html")
    # The argv is recorded so a surprising row can be reproduced by hand.
    assert invocation.argv[:2] == ("codex", "exec")


def test_a_timeout_is_reported_as_a_timeout(tmp_path: Path, monkeypatch):
    bindir = tmp_path / "bin"
    _write_agent(bindir, "slowagent", "#!/bin/sh\nsleep 30\n")
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")

    invocation = invoke_agent(GenericProfile("slow", "slowagent"), "hi", timeout_s=2)

    assert not invocation.produced_document
    assert "timed out" in invocation.error
    assert invocation.exit_code is None


def test_an_agent_that_writes_nothing_is_reported_honestly(tmp_path: Path, monkeypatch):
    bindir = tmp_path / "bin"
    _write_agent(bindir, "muteagent", "#!/bin/sh\necho 'I thought about it'\n")
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")

    invocation = invoke_agent(GenericProfile("mute", "muteagent"), "hi", timeout_s=30)

    assert invocation.exit_code == 0
    assert not invocation.produced_document
    assert "no HTML" in invocation.error
    # Its chatter is kept, because that is how you work out why it stalled.
    assert "I thought about it" in invocation.stdout_tail


def test_output_is_trimmed_so_a_report_stays_readable(tmp_path: Path, monkeypatch):
    bindir = tmp_path / "bin"
    _write_agent(bindir, "loudagent", "#!/bin/sh\nyes 'A' | head -c 50000\n")
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")

    invocation = invoke_agent(GenericProfile("loud", "loudagent"), "hi", timeout_s=30)

    assert len(invocation.stdout_tail) <= agents.OUTPUT_TAIL_CHARS


def test_the_workdir_is_reported_so_a_run_can_be_inspected(fake_bin: Path):
    invocation = invoke_agent(CodexProfile(), "hi", timeout_s=30)
    assert Path(invocation.workdir).is_dir()


def test_run_agent_for_brief_reads_the_document_back(fake_bin: Path):
    attempt = run_agent_for_brief(CodexProfile(), "make a scene", timeout_s=30)
    assert attempt.ok
    assert "data-composition-id" in attempt.document
    assert attempt.to_dict()["document_chars"] == len(attempt.document)


# -- the opt-in gate --------------------------------------------------------


def test_the_default_matrix_never_invokes_an_agent_even_when_installed(monkeypatch):
    """The single most important guarantee in Phase 7.

    codex and claude really are installed on this machine, so if the opt-in
    gate ever regressed this test would fire a live, billable API call. We
    make that impossible to do quietly.
    """

    def _boom(*args, **kwargs):
        raise AssertionError("a real agent was invoked without opt-in")

    monkeypatch.setattr(hm, "run_agent_for_brief", _boom)

    report = hm.run_matrix_demo()

    for name in ("codex", "claude"):
        assert report["cells"][("good_artifact", name)]["skipped"]


def test_an_enabled_agent_produces_a_real_measurement(fake_bin: Path):
    harness = hm.ExternalAgentHarness("codex", "codex", enabled=True, timeout_s=30)

    result = harness("", brief="good_artifact", task="make a scene")

    assert not result.skipped
    assert result.passed
    assert result.live_agent
    # Judged by our gates, so the row carries our gate names, not the agent's
    # opinion of itself.
    assert "static_html" in result.gates
    assert result.attempt["exit_code"] == 0


def test_an_enabled_agent_that_produces_nothing_is_skipped_not_failed(
    tmp_path: Path, monkeypatch
):
    """A skipped row is not a verdict on the agent's ability.

    If the agent never ran, reporting "codex: 0/2 passed" would publish a
    number that is really just "the network was down".
    """
    bindir = tmp_path / "bin"
    _write_agent(bindir, "codex", "#!/bin/sh\nexit 1\n")
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")

    harness = hm.ExternalAgentHarness("codex", "codex", enabled=True, timeout_s=30)

    result = harness("", brief="good_artifact", task="make a scene")

    assert result.skipped
    assert not result.passed
    assert result.live_agent  # we really did try
    assert "no HTML" in result.detail


def test_an_external_row_ignores_the_reference_document(fake_bin: Path):
    """It must be judged on what it made, not on someone else's artifact."""
    harness = hm.ExternalAgentHarness("codex", "codex", enabled=True, timeout_s=30)

    result = harness("<html>someone elses</html>", brief="b", task="make a scene")

    assert result.attempt is not None
    assert "someone elses" not in result.detail


# -- the prompt contract ----------------------------------------------------


def test_the_prompt_names_the_exact_file_expected():
    prompt = agents.build_prompt("a launch title card")
    assert "index.html" in prompt
    assert "a launch title card" in prompt


def test_the_prompt_forbids_external_assets():
    """Our gates measure inline markup; a CDN link would be unmeasurable."""
    prompt = agents.build_prompt("anything")
    assert "No external assets" in prompt


def test_the_prompt_tells_the_agent_to_act_not_describe():
    prompt = agents.build_prompt("anything")
    assert "Do not describe what you would write" in prompt


def test_spec_context_is_optional_and_absent_without_a_spec():
    assert agents.spec_context_for(None) is None


def test_the_bench_still_works_if_the_agent_bridge_is_deleted(monkeypatch):
    """The bridge is an optional leaf; the bench may not depend on it."""
    import builtins

    real_import = builtins.__import__

    def _blocked(name, *args, **kwargs):
        if "bridge" in name:
            raise ImportError("bridge deleted")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    assert agents.spec_context_for(object()) is None


# -- reporting --------------------------------------------------------------


def test_json_safe_flattens_tuple_keys():
    report = hm.run_matrix_demo()
    with pytest.raises(TypeError):
        json.dumps(report)
    flat = hm.json_safe(report)
    assert json.dumps(flat)  # serialises
    assert "good_artifact::colophon" in flat["cells"]


def test_live_rows_are_marked_in_the_table(fake_bin: Path):
    report = hm.run_matrix_demo(agents=True, timeout_s=30)
    table = hm.format_matrix(report)
    assert "PASS*" in table
    assert "not a" in table  # the non-reproducibility footnote


def test_the_table_explains_every_skip():
    report = hm.run_matrix_demo()
    table = hm.format_matrix(report)
    assert "skip: codex:" in table


# -- CLI --------------------------------------------------------------------


def test_cli_bench_runs_offline_by_default(capsys):
    assert main(["bench"]) == 0
    out = capsys.readouterr().out
    assert "colophon" in out
    assert "external agents were not run" in out


def test_cli_bench_json_is_serialisable(capsys):
    assert main(["bench", "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert "good_artifact::colophon" in parsed["cells"]


def test_cli_bench_with_agents_measures_a_real_artifact(fake_bin: Path, capsys):
    assert main(["bench", "--agents", "--timeout", "30"]) == 0
    out = capsys.readouterr().out
    assert "PASS*" in out
    assert "external agents were not run" not in out
