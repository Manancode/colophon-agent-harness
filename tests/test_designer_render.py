"""Phase 6 tests: the design loop driving the renderer (or degrading gracefully).

These prove the new claim of Phase 6: when a renderer is wired the loop runs
the *full* gate set against a real artifact and feeds those findings into the
same repair router; when the renderer cannot run it degrades to the spec level
and records an honest attestation instead of crashing or silently shipping.
"""

from pathlib import Path

from colophon.harness import designer
from colophon.harness.designer import DesignSession, DesignerSettings, run_design_loop
from colophon.harness.render import (
    RenderCapability,
    RenderOutcome,
    RuntimeRenderDriver,
    resolve_render_capability,
)
from colophon.qa.runner import StageResult
from colophon.spec.schema import VideoSpec
from colophon.timeline.plan import build_plan


# --------------------------------------------------------------------------
# Spec builders (mirror the Phase 5 suite)
# --------------------------------------------------------------------------


def _valid_spec(d1=4.0, d2=4.0) -> VideoSpec:
    from colophon.spec.schema import Brand, Canvas, Claim, Scene, Timeline

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


def _with_duration(spec: VideoSpec, scene_id: str, value: float) -> VideoSpec:
    from dataclasses import replace

    scenes = [
        replace(s, duration_s=value) if s.scene_id == scene_id else s
        for s in spec.scenes
    ]
    return replace(spec, scenes=tuple(scenes))


# --------------------------------------------------------------------------
# Stub drivers / agents
# --------------------------------------------------------------------------


class _DecliningDriver:
    """A driver that claims to render but produces no usable artifact."""

    def render(self, *, spec, plan, workspace):
        return RenderOutcome(
            rendered=False, context={}, error="renderer not provisioned at /tmp/fake"
        )


class _RenderedDriver:
    """A driver that reports success but hands back an incomplete artifact.

    The full gate set then runs against that artifact; here we intentionally
    omit the video so a render-dependent gate has something to flag.
    """

    def __init__(self):
        self.calls = 0

    def render(self, *, spec, plan, workspace):
        self.calls += 1
        return RenderOutcome(
            rendered=True,
            context={"document": "", "scene_fragments": {}, "video_path": None},
            attempt="fake",
        )


class _DecliningAgent:
    def __init__(self):
        self.calls = []

    def repair(self, *, spec, findings):
        self.calls.append(1)
        return None


# --------------------------------------------------------------------------
# Capability probe
# --------------------------------------------------------------------------


def test_resolve_render_capability_shape():
    cap = resolve_render_capability()
    assert isinstance(cap, RenderCapability)
    assert isinstance(cap.available, bool)
    assert isinstance(cap.reason, str)
    d = cap.to_dict()
    assert set(d) >= {"available", "reason", "missing"}


# --------------------------------------------------------------------------
# Graceful degradation
# --------------------------------------------------------------------------


def test_default_run_is_spec_level_without_render_metadata():
    bad = _with_duration(_valid_spec(), "s2", 0.0)
    session = run_design_loop(bad)
    assert session.shippable
    assert session.render_requested is False
    assert session.render_available is False
    assert session.render_attestation is None
    assert session.render_error is None


def test_driver_declines_is_recorded_as_attestation():
    """When the driver cannot render, the loop still mechanically fixes the
    spec and records *why* the full gates did not run -- it never pretends the
    video was checked."""
    bad = _with_duration(_valid_spec(), "s2", 0.0)
    session = run_design_loop(bad, driver=_DecliningDriver())
    assert session.shippable
    assert session.render_requested is True
    assert session.render_available is False
    assert session.render_attestation is not None
    assert "not run" in session.render_attestation
    assert "renderer not provisioned" in session.render_attestation
    # Mechanical fix still applied despite the render layer being unavailable.
    by_id = {s.scene_id: s.duration_s for s in session.final_spec.scenes}
    assert by_id["s2"] == designer.DEFAULT_SCENE_DURATION_S


# --------------------------------------------------------------------------
# Render-level findings flow through the router
# --------------------------------------------------------------------------


def _fake_render_blocker(spec, *, video_path=None, **_):
    """A render-dependent gate: blocks when no video was produced."""
    if video_path is None:
        return StageResult(
            stage_id="fake_render",
            passed=False,
            problems=["no video from fake render"],
        )
    return StageResult(stage_id="fake_render", passed=True, problems=[])


def test_render_level_finding_routes_to_llm_seam_and_aborts():
    """A blocker produced by the full gate set (only run when a real artifact
    exists) is fed into the same router. With the agent unwired it declines and
    the loop aborts after the repeat limit -- proving render findings reach the
    judgment path, not some separate code path."""
    agent = _DecliningAgent()
    session = run_design_loop(
        _valid_spec(),
        llm=agent,
        driver=_RenderedDriver(),
        render_stages=[_fake_render_blocker],
    )
    assert session.render_requested is True
    assert session.render_available is True
    assert session.aborted is True
    assert session.turns_used == designer._MAX_REPEATED_VALIDATION_ERRORS
    # The turn that detects the 4th repeat aborts without one more agent call.
    assert len(agent.calls) == designer._MAX_REPEATED_VALIDATION_ERRORS - 1
    assert "<uncoded>" in (session.abort_reason or "")


# --------------------------------------------------------------------------
# Production driver degrades without touching the network
# --------------------------------------------------------------------------


def test_runtime_driver_declines_when_not_provisioned(tmp_path):
    """The real driver must never auto-install or hang. In an environment
    without a provisioned renderer it declines (rendered=False) with a reason,
    and does not raise."""
    spec = _valid_spec()
    plan = build_plan(spec)
    driver = RuntimeRenderDriver()
    outcome = driver.render(spec=spec, plan=plan, workspace=tmp_path)
    assert isinstance(outcome, RenderOutcome)
    assert outcome.rendered is False
    assert outcome.error  # tells the user what to do


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_design_render_degrades(tmp_path):
    """`colophon design --render` in an environment without a provisioned
    renderer must still mechanically fix the spec and report the attestation,
    not crash or claim a video was verified."""
    from colophon.cli import main

    spec = _with_duration(_valid_spec(), "s2", 0.0)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(__import__("json").dumps(spec.to_dict()))
    out = tmp_path / "out"

    rc = main(["design", str(spec_path), "--out", str(out), "--render", "--max-turns", "30"])
    assert rc == 0
    session_doc = __import__("json").loads((out / "design-session.json").read_text())
    assert session_doc["shippable"] is True
    assert session_doc["render_requested"] is True
    assert session_doc["render_available"] is False
    assert "not run" in (session_doc["render_attestation"] or "")

    designed = VideoSpec.from_dict(
        __import__("json").loads((out / "spec.designed.json").read_text())
    )
    by_id = {s.scene_id: s for s in designed.scenes}
    assert by_id["s2"].duration_s == designer.DEFAULT_SCENE_DURATION_S
