"""Tests for the MCP tool surface and the gate catalog behind it.

These call the tool functions directly. They never start a server and never
import an MCP library, which is deliberate: it keeps the whole suite runnable
without the optional dependency, and it is the reason the tools are plain
functions with a thin registration table in front of them rather than
decorated closures.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from colophon import mcp_server
from colophon.qa import pipeline as qa_pipeline
from colophon.runs import layout as run_layout

from .conftest import scene, spec_dict, two_scene_spec


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def write_spec(path: Path, **overrides) -> Path:
    path.write_text(json.dumps(spec_dict(**overrides)), encoding="utf-8")
    return path


def write_raw_spec(path: Path, raw: dict) -> Path:
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# the gate catalog
# --------------------------------------------------------------------------


def test_the_spec_level_set_is_four_gates():
    assert len(qa_pipeline.spec_gate_fns()) == 4


def test_the_full_set_is_fourteen_gates():
    assert len(qa_pipeline.full_gate_fns()) == 14


def test_every_gate_has_a_unique_stage_id():
    ids = [fn.__name__ for fn in qa_pipeline.full_gate_fns()]
    assert len(set(ids)) == len(ids)


def test_every_spec_level_gate_is_also_in_the_full_set():
    spec_ids = {fn.__name__ for fn in qa_pipeline.spec_gate_fns()}
    full_ids = {fn.__name__ for fn in qa_pipeline.full_gate_fns()}
    assert spec_ids <= full_ids


def test_every_gate_is_classified_by_the_artifact_it_needs():
    """The classification is derived; this pins what it currently derives."""
    catalog = {g.stage_id: g.needs for g in qa_pipeline.gate_catalog(qa_pipeline.full_gate_fns())}
    spec_ids = {fn.__name__ for fn in qa_pipeline.spec_gate_fns()}

    for stage_id in spec_ids:
        assert catalog[stage_id] == "spec", stage_id

    assert qa_pipeline.NEEDS_PROJECT in catalog.values()
    assert qa_pipeline.NEEDS_VIDEO in catalog.values()


def test_a_gate_that_only_accepts_a_video_is_not_a_video_tier_gate():
    """Accepting an artifact is not the same as needing one.

    ``scene_structure`` takes ``video_path`` for one extra check and does real
    project-level work without it. Classifying it as video-tier told an agent
    it had to render before this gate could speak, which is false — it catches
    a zero-duration scene straight off the plan.
    """
    from colophon.qa.stages.structure import scene_structure

    assert qa_pipeline.needs_for(scene_structure) == qa_pipeline.NEEDS_PROJECT


def test_a_gate_that_cannot_run_without_a_video_stays_video_tier():
    """The other half of the same distinction, so the fix cannot overcorrect."""
    from colophon.qa.stages.media import media_contract

    assert qa_pipeline.needs_for(media_contract) == qa_pipeline.NEEDS_VIDEO


def test_gate_needs_rejects_an_unknown_tier():
    with pytest.raises(ValueError):
        qa_pipeline.gate_needs("vibes")


def test_every_gate_declares_a_tier_the_catalog_can_report():
    """No gate may fall through to a tier nobody can see."""
    for info in qa_pipeline.gate_catalog(qa_pipeline.full_gate_fns()):
        assert info.needs in qa_pipeline.TIERS, info.stage_id


def test_gates_needing_no_more_than_spec_is_exactly_the_spec_level_set():
    full = qa_pipeline.full_gate_fns()
    filtered = qa_pipeline.gates_needing_no_more_than(full, qa_pipeline.NEEDS_SPEC)
    assert [fn.__name__ for fn in filtered] == [
        fn.__name__ for fn in qa_pipeline.spec_gate_fns()
    ]


def test_gates_needing_no_more_than_rejects_an_unknown_tier():
    with pytest.raises(ValueError):
        qa_pipeline.gates_needing_no_more_than(qa_pipeline.full_gate_fns(), "vibes")


def test_every_gate_can_describe_itself():
    """A gate with no summary is a gate an agent cannot reason about."""
    for info in qa_pipeline.gate_catalog(qa_pipeline.full_gate_fns()):
        assert info.summary, info.stage_id


# --------------------------------------------------------------------------
# the tool functions
# --------------------------------------------------------------------------


def test_every_registered_tool_is_named_for_colophon():
    for _fn, name, description in mcp_server.TOOLS:
        assert name.startswith("colophon_")
        assert description


def test_every_public_tool_function_is_registered():
    registered = {fn for fn, _name, _desc in mcp_server.TOOLS}
    for name in ("gates", "doctor", "init_run", "validate", "plan", "qa", "design"):
        assert getattr(mcp_server, name) in registered, name


def test_a_raising_tool_reports_the_failure_instead_of_propagating_it():
    """An MCP-level error is a protocol event; an agent needs a readable one."""
    def boom(run_dir: str) -> dict:
        raise FileNotFoundError(f"no spec at {run_dir}/spec.json")

    result = mcp_server.guarded(boom)("/tmp/whatever")

    assert result["ok"] is False
    assert "no spec at" in result["error"]


def test_a_working_tool_is_passed_through_untouched():
    result = mcp_server.guarded(lambda: {"ok": True, "state": "ready"})()
    assert result == {"ok": True, "state": "ready"}


def test_guarding_preserves_the_function_identity_a_harness_reads():
    """The name and docstring are part of what a harness shows an agent."""

    def colophon_example(run_dir: str) -> dict:
        """An example tool."""
        return {"ok": True}

    wrapped = mcp_server.guarded(colophon_example)

    assert wrapped.__name__ == "colophon_example"
    assert wrapped.__doc__ == "An example tool."


def test_the_gates_tool_describes_every_gate():
    result = mcp_server.gates()
    assert result["ok"] is True
    assert result["gate_count"] == 14
    assert len(result["gates"]) == 14
    assert sum(1 for g in result["gates"] if g["spec_level"]) == 4
    for gate in result["gates"]:
        assert gate["needs"] in ("spec", "project", "video")


def test_the_doctor_tool_reports_the_runtime():
    result = mcp_server.doctor()
    assert result["ok"] is True
    assert isinstance(result["ready"], bool)
    assert "cache_key" in result


def test_init_freezes_the_spec_and_reports_its_hash(tmp_path):
    spec_path = write_spec(tmp_path / "spec.json")
    run_dir = tmp_path / "run"

    result = mcp_server.init_run(str(spec_path), str(run_dir))

    assert result["ok"] is True
    assert result["spec_sha256"]
    assert result["scene_count"] == 1
    assert (run_dir / "spec.json").is_file()
    assert (run_dir / "spec.sha256").is_file()


def good_spec() -> dict:
    """Two scenes totalling 6s.

    Not one scene: the delivery contract floors the *total* at 5s, so a
    single 2s scene is blocked for a reason that has nothing to do with what
    these tests are checking.
    """
    raw = two_scene_spec()
    raw["scenes"][0]["duration_s"] = 3.0
    raw["scenes"][1]["duration_s"] = 3.0
    return raw


def test_validate_needs_no_artifact_and_clears_a_good_spec(tmp_path):
    spec_path = write_raw_spec(tmp_path / "spec.json", good_spec())
    run_dir = tmp_path / "run"
    mcp_server.init_run(str(spec_path), str(run_dir))

    result = mcp_server.validate(str(run_dir))

    assert result["ok"] is True
    assert result["state"] in ("ready", "ready_with_warnings")
    assert result["gates_run"] == 4


def test_validate_blocks_a_spec_with_a_non_positive_duration(tmp_path):
    spec_path = write_spec(tmp_path / "spec.json", scenes=[scene("s1", duration_s=0)])
    run_dir = tmp_path / "run"
    mcp_server.init_run(str(spec_path), str(run_dir))

    result = mcp_server.validate(str(run_dir))

    assert result["state"] == "blocked"
    assert result["blockers"]


def test_validate_does_not_blame_a_missing_artifact_for_a_spec_defect(tmp_path):
    """The hint has to name the right problem, not just any problem.

    `validate` runs only the four spec-level gates, which never read an
    artifact. Telling an agent "nothing has been emitted yet" for a spec with a
    zero-second scene would send it off to emit, when the spec is what is
    wrong. The artifact explanation belongs to `qa` and nowhere else.
    """
    spec_path = write_spec(tmp_path / "spec.json", scenes=[scene("s1", duration_s=0)])
    run_dir = tmp_path / "run"
    mcp_server.init_run(str(spec_path), str(run_dir))

    result = mcp_server.validate(str(run_dir))

    assert result["scope"] == "spec"
    assert "emit" not in result["hint"]
    assert result["hint"].startswith("fix the blockers")


def test_validate_on_a_run_with_no_spec_says_so(tmp_path):
    with pytest.raises(FileNotFoundError):
        mcp_server.validate(str(tmp_path / "nope"))


def test_plan_writes_the_timeline(tmp_path):
    spec_path = write_spec(tmp_path / "spec.json")
    run_dir = tmp_path / "run"
    mcp_server.init_run(str(spec_path), str(run_dir))

    result = mcp_server.plan(str(run_dir))

    assert result["ok"] is True
    assert Path(result["plan_path"]).is_file()
    assert result["total_duration_s"] > 0
    assert result["scenes"][0]["scene_id"] == "s1"


def test_qa_without_an_attempt_refuses_to_guess(tmp_path):
    spec_path = write_spec(tmp_path / "spec.json")
    run_dir = tmp_path / "run"
    mcp_server.init_run(str(spec_path), str(run_dir))

    # No attempt exists, so there is nothing to check. Saying "ready" here
    # would be a lie; the tool raises instead and the MCP layer reports it.
    with pytest.raises(FileNotFoundError):
        mcp_server.qa(str(run_dir))


def test_qa_before_emit_blocks_and_explains_why(tmp_path):
    """The failure mode this tool exists to prevent.

    Before anything is emitted, the project- and video-tier gates report
    "nothing to check" and colophon counts that as a blocker — correctly, since
    failing closed is the point. An agent reading only the blocker list would
    conclude it had broken something. The hint has to say otherwise.
    """
    spec_path = write_spec(tmp_path / "spec.json")
    run_dir = tmp_path / "run"
    mcp_server.init_run(str(spec_path), str(run_dir))
    run_layout.begin_attempt(run_layout.run_paths(run_dir), 1)

    result = mcp_server.qa(str(run_dir))

    assert result["ok"] is True
    assert result["state"] == "blocked"
    assert "emit" in result["hint"]
    assert (run_dir / "attempts/01/qa/qa-report.json").is_file()


def test_design_repairs_a_non_positive_duration(tmp_path):
    # Two scenes on purpose. The mechanical remedy clamps a bad duration to
    # 4.0s, and the delivery contract floors the *total* at 5.0s — so a
    # one-scene spec is unreachable by mechanical repair alone, and this test
    # would be asserting something the loop is right to refuse.
    raw = two_scene_spec()
    raw["scenes"][0]["duration_s"] = 0
    spec_path = write_raw_spec(tmp_path / "spec.json", raw)
    out_dir = tmp_path / "designed"

    result = mcp_server.design(str(spec_path), out_dir=str(out_dir))

    assert result["ok"] is True
    assert result["shippable"] is True
    assert result["turns_used"] >= 1
    assert (out_dir / "spec.designed.json").is_file()
    assert (out_dir / "design-session.json").is_file()


def test_design_stops_blocked_on_something_it_cannot_mechanically_fix(tmp_path):
    """A one-scene spec whose total is under the delivery floor.

    The loop can clamp the duration but cannot invent a second scene, so the
    honest outcome is `blocked` — not a silent ship, and not a spin.
    """
    spec_path = write_spec(tmp_path / "spec.json", scenes=[scene("s1", duration_s=0)])

    result = mcp_server.design(str(spec_path))

    assert result["shippable"] is False
    assert result["state"] == "blocked"
    assert result["blockers"]


def test_design_without_an_out_dir_writes_nothing(tmp_path):
    spec_path = write_spec(tmp_path / "spec.json")

    result = mcp_server.design(str(spec_path))

    assert result["ok"] is True
    assert result["written"] == {}


# --------------------------------------------------------------------------
# server registration
# --------------------------------------------------------------------------


def test_build_server_registers_every_tool():
    """The registration path, which nothing else in this file exercises.

    Every test above calls a tool function directly, which is the point — but
    it means a broken registration could pass the whole suite. It did: fastmcp
    changed ``add_tool`` from taking a function plus ``name=``/``description=``
    keywords to taking a ``Tool`` object, and the mismatch surfaced as a
    ``TypeError`` when starting the server, after 445 other tests had gone
    green.

    Skipped without the optional dependency, which is why the dependency is
    optional.
    """
    pytest.importorskip("fastmcp", reason="optional MCP dependency not installed")

    server = mcp_server.build_server()

    manager = getattr(server, "_tool_manager", None)
    assert manager is not None, "fastmcp server exposes no tool manager"

    for _, name, _ in mcp_server.TOOLS:
        tool = asyncio.run(manager.get_tool(name))
        assert tool is not None, f"{name} was not registered"
        assert tool.name == name
