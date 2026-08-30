"""Tests for the Phase 5 design-harness loop.

These prove the core claim of the loop: a blocker with a registered,
deterministic remedy (today: a non-positive scene duration) is fixed for free
and the run becomes shippable, while anything that needs judgment either gets
handed to a repair agent or -- when none is wired -- makes the loop stop in the
blocked state rather than ship a broken spec or spin forever.
"""

import json
from dataclasses import replace

from colophon.harness import designer
from colophon.harness.designer import (
    DesignSession,
    DesignerSettings,
    MECHANICAL_CODES,
    UnwiredRepairAgent,
    route_blockers,
    run_design_loop,
)
from colophon.qa.taxonomy import classify
from colophon.repair.apply import RepairOp
from colophon.spec.schema import Brand, Canvas, Claim, Scene, Timeline, VideoSpec


# --------------------------------------------------------------------------
# Spec builders
# --------------------------------------------------------------------------


def _valid_spec(d1=4.0, d2=4.0) -> VideoSpec:
    """A two-scene spec that clears every spec-level gate.

    Each scene is 4s, so the total (8s) clears the delivery envelope and the
    only way to make it *block* is to inject a fault.
    """
    return VideoSpec(
        spec_id="test-spec",
        title="Test launch",
        canvas=Canvas(width=1920, height=1080, fps=30, background="#0B0B12"),
        brand=Brand(
            name="Testco",
            tokens={"bg": "#0B0B12", "fg": "#F5F5F7", "accent": "#4F8CFF"},
        ),
        timeline=Timeline(policy="adjacent", overlap_s=0.0, transition="cut", transition_ms=0),
        claims=(
            Claim("t1", "Ship faster", "title", "brief#pos"),
            Claim("n1", "Teams ship faster, with fewer regressions.", "narration", "brief#prob"),
            Claim("t2", "Built for engineers", "title", "brief#aud"),
            Claim("n2", "Every run is hashed and reproducible.", "narration", "brief#cap"),
        ),
        scenes=(
            Scene("s1", "hook", "hero-centered", d1, title_claim_id="t1", narration_claim_id="n1"),
            Scene("s2", "problem", "statement-left", d2, title_claim_id="t2", narration_claim_id="n2"),
        ),
    )


def _single_spec(duration=2.0) -> VideoSpec:
    """One scene. With the default 2s it passes spec_validate but fails the
    delivery envelope (total < 5s) -- an *uncoded* blocker nothing mechanical
    can fix, exactly the case the loop must not silently pass."""
    return VideoSpec(
        spec_id="test-spec",
        title="Test",
        canvas=Canvas(width=1920, height=1080, fps=30, background="#0B0B12"),
        brand=Brand(
            name="Testco",
            tokens={"bg": "#0B0B12", "fg": "#F5F5F7", "accent": "#4F8CFF"},
        ),
        timeline=Timeline(policy="adjacent", overlap_s=0.0, transition="cut", transition_ms=0),
        claims=(
            Claim("t1", "Ship faster", "title", "brief#b"),
            Claim("n1", "Faster regressions.", "narration", "brief#b"),
        ),
        scenes=(
            Scene("s1", "hook", "hero-centered", duration, title_claim_id="t1", narration_claim_id="n1"),
        ),
    )


def _with_duration(spec: VideoSpec, scene_id: str, value: float) -> VideoSpec:
    scenes = [
        replace(s, duration_s=value) if s.scene_id == scene_id else s
        for s in spec.scenes
    ]
    return replace(spec, scenes=tuple(scenes))


# --------------------------------------------------------------------------
# Stub repair agents (the judgment path)
# --------------------------------------------------------------------------


class _FixingAgent:
    def __init__(self):
        self.calls = []

    def repair(self, *, spec, findings):
        self.calls.append((spec, findings))
        scenes = [replace(s, duration_s=6.0) for s in spec.scenes]
        return replace(spec, scenes=tuple(scenes))


class _DecliningAgent:
    def __init__(self):
        self.calls = []

    def repair(self, *, spec, findings):
        self.calls.append(1)
        return None


class _NoopAgent:
    def __init__(self):
        self.calls = []

    def repair(self, *, spec, findings):
        self.calls.append(1)
        return spec  # unchanged: still blocked


# --------------------------------------------------------------------------
# Routing / registry
# --------------------------------------------------------------------------


def test_mechanical_codes_registry_is_exactly_duration():
    assert MECHANICAL_CODES == frozenset({"spec.scene.duration"})


def test_route_blockers_splits_mechanical_and_judgment():
    mech = classify("spec_validate", "x", "spec.scene.duration")
    uncoded = classify("delivery_contract", "some message")  # code None
    taste = classify("scene_structure", "blank frame", "structure.black_frame")
    mechanical, llm = route_blockers([mech, uncoded, taste])
    assert [f.code for f in mechanical] == ["spec.scene.duration"]
    assert set(f.code for f in llm) == {None, "structure.black_frame"}


def test_mech_fix_clamps_all_nonpositive_durations():
    spec = _with_duration(_with_duration(_valid_spec(), "s2", -1.0), "s1", 0.0)
    ops, claim_edits = designer.MECHANICAL_REMEDIES["spec.scene.duration"](spec, None)
    assert claim_edits == {}
    assert sorted((o.scene_id, o.field, o.value) for o in ops) == [
        ("s1", "duration_s", designer.DEFAULT_SCENE_DURATION_S),
        ("s2", "duration_s", designer.DEFAULT_SCENE_DURATION_S),
    ]


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------


def test_mechanical_fix_reaches_shippable_without_an_agent():
    bad = _with_duration(_valid_spec(), "s2", 0.0)
    session = run_design_loop(bad)
    assert isinstance(session, DesignSession)
    assert session.shippable
    assert not session.aborted
    # One turn: apply the mechanical patch, re-check, done.
    assert session.turns_used == 1
    assert session.turns[0].mechanical_codes == ("spec.scene.duration",)
    fixed = {s.scene_id: s.duration_s for s in session.final_spec.scenes}
    assert fixed["s2"] == designer.DEFAULT_SCENE_DURATION_S
    assert fixed["s1"] == 4.0


def test_transitive_clearing_needs_no_agent():
    """A bad duration also trips the delivery + timeline gates (uncoded). Those
    are symptoms of the same root cause, so fixing the duration clears them
    without ever calling an agent."""
    bad = _with_duration(_valid_spec(), "s2", 0.0)
    session = run_design_loop(bad, llm=None)
    # No agent was ever consulted.
    assert session.turns[0].llm_codes == () or session.turns[0].note.startswith(
        "mechanical"
    )
    assert session.shippable


def test_aborts_after_repeated_identical_uncoded_blocker():
    spec = _single_spec(2.0)  # only an uncoded delivery blocker, no agent
    session = run_design_loop(spec, settings=DesignerSettings(max_turns=30))
    assert session.aborted
    assert session.turns_used == designer._MAX_REPEATED_VALIDATION_ERRORS
    assert session.assessment.state == "blocked"
    assert None in {f.code for f in session.assessment.blockers}


def test_llm_seam_can_clear_uncoded_blocker():
    agent = _FixingAgent()
    session = run_design_loop(_single_spec(2.0), llm=agent)
    assert session.shippable
    assert session.turns_used == 2
    assert len(agent.calls) >= 1
    assert session.final_spec.total_duration_s >= 5.0


def test_llm_declining_aborts():
    agent = _DecliningAgent()
    session = run_design_loop(_single_spec(2.0), llm=agent)
    assert session.aborted
    assert session.turns_used == designer._MAX_REPEATED_VALIDATION_ERRORS
    # The turn that *detects* the 4th repeat aborts without one more agent call.
    assert len(agent.calls) == designer._MAX_REPEATED_VALIDATION_ERRORS - 1


def test_llm_noop_aborts_after_repeat():
    agent = _NoopAgent()
    session = run_design_loop(_single_spec(2.0), llm=agent)
    assert session.aborted
    assert session.turns_used == designer._MAX_REPEATED_VALIDATION_ERRORS
    assert len(agent.calls) == designer._MAX_REPEATED_VALIDATION_ERRORS - 1


def test_budget_exhaustion_is_reported():
    # A pathological agent that "fixes" into a still-blocked but *different*
    # spec each turn would otherwise never repeat; the budget caps it. The
    # wobble is large enough to survive frame quantization (so the blocker
    # message keeps changing and the repeat-guard never fires).
    class _WobblingAgent:
        def __init__(self):
            self.calls = []

        def repair(self, *, spec, findings):
            self.calls.append(1)
            scenes = [
                replace(s, duration_s=2.0 + 0.1 * len(self.calls)) for s in spec.scenes
            ]
            return replace(spec, scenes=tuple(scenes))

    agent = _WobblingAgent()
    session = run_design_loop(
        _single_spec(2.0), llm=agent, settings=DesignerSettings(max_turns=7)
    )
    assert session.aborted
    assert session.turns_used == 7
    assert len(agent.calls) == 7
    assert "budget" in (session.abort_reason or "")


def test_session_serializes():
    session = run_design_loop(_with_duration(_valid_spec(), "s2", 0.0))
    d = session.to_dict()
    assert d["shippable"] is True
    assert d["turns_used"] == 1
    assert len(d["turns"]) == 1
    assert "assessment" in d


def test_unwired_agent_is_the_default():
    assert isinstance(UnwiredRepairAgent().repair(spec=_valid_spec(), findings=[]), type(None))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_design_writes_outputs(tmp_path):
    from colophon.cli import main

    spec = _with_duration(_valid_spec(), "s2", 0.0)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec.to_dict()))
    out = tmp_path / "out"

    rc = main(["design", str(spec_path), "--out", str(out), "--max-turns", "30"])
    assert rc == 0
    assert (out / "spec.designed.json").is_file()
    assert (out / "design-session.json").is_file()

    designed = VideoSpec.from_dict(
        json.loads((out / "spec.designed.json").read_text())
    )
    by_id = {s.scene_id: s for s in designed.scenes}
    assert by_id["s2"].duration_s == designer.DEFAULT_SCENE_DURATION_S
