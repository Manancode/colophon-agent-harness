"""Structural checks: the six ways a scene can be scheduled and draw nothing.

The load-bearing test here is the first one. A gate that never fires is worse
than no gate, because it reports green; so these tests prove both that the
gate is silent on real output and that it fires on each broken shape.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from colophon.presentation.treatments import MOTIONS, baseline_motion
from colophon.qa.stages import structure as st
from colophon.qa.taxonomy import FAILURE_MODES
from colophon.renderers.hyperframes.emit import render_document, scene_fragments
from colophon.spec.schema import (
    Brand,
    Canvas,
    Claim,
    Scene,
    Timeline,
    VideoSpec,
)
from colophon.timeline.plan import build_plan

TITLE = "Build the agent that lives in chat"
NARRATION = "Across 200 pilot repos, it cut review time by half."


def _spec(motion: str = "fade-rise", treatment: str = "hero-centered") -> VideoSpec:
    return VideoSpec(
        spec_id="structure-probe",
        spec_version="0.1",
        title="structure probe",
        brand=Brand(
            name="Probe",
            tokens={"accent": "#4F8CFF", "bg": "#0B0B12", "fg": "#F5F5F7",
                    "hair": "#E2E2E5"},
        ),
        canvas=Canvas(width=1920, height=1080, fps=30, background="#0B0B12"),
        claims=[
            Claim(claim_id="c-title", kind="title", source="probe", text=TITLE),
            Claim(claim_id="c-narr", kind="narration", source="probe", text=NARRATION),
        ],
        scenes=[
            Scene(
                scene_id="s1",
                role="hook",
                treatment=treatment,
                motion=motion,
                duration_s=4.0,
                title_claim_id="c-title",
                narration_claim_id="c-narr",
            )
        ],
        timeline=Timeline(policy="adjacent", transition="cut",
                          transition_ms=0, overlap_s=0.0),
    )


def _run(motion: str = "fade-rise"):
    spec = _spec(motion)
    plan = build_plan(spec)
    return spec, plan, render_document(spec, plan), scene_fragments(spec, plan)


# --- no false positives on real output ------------------------------------


@pytest.mark.parametrize("motion", ["fade-rise", "word-sweep", "thinking-pulse"])
def test_real_emitted_document_passes(motion):
    """The gate must be silent on output the emitter actually produces.

    If this fails, the gate is reporting a defect that does not exist, and
    every real run starts red.
    """
    spec, plan, doc, frags = _run(motion)
    r = st.scene_structure(spec, plan, doc, frags)
    assert r.passed, r.problems


def test_real_emitted_document_reports_nothing_for_a_multi_scene_run():
    # hero-centered (word-sweep) + stat-hero (thinking-pulse): the two shapes
    # that differ most in the markup they emit. Keywords throughout: Scene
    # takes duration_s *before* motion, and a positional list silently builds
    # a scene whose duration is the string "word-sweep".
    spec = _spec("word-sweep")
    spec = VideoSpec(
        **{
            **spec.__dict__,
            "scenes": (
                Scene(scene_id="s1", role="hook", treatment="hero-centered",
                      duration_s=4.0, motion="word-sweep",
                      title_claim_id="c-title", narration_claim_id="c-narr"),
                Scene(scene_id="s2", role="proof", treatment="stat-hero",
                      duration_s=4.0, motion="thinking-pulse",
                      title_claim_id="c-title", narration_claim_id="c-narr"),
            ),
        }
    )
    plan = build_plan(spec)
    r = st.scene_structure(spec, plan, render_document(spec, plan),
                           scene_fragments(spec, plan))
    assert r.passed, r.problems


# --- no visuals -----------------------------------------------------------


def test_scene_with_no_content_is_flagged():
    plan = SimpleNamespace(windows=())
    r = st.scene_structure(None, plan, "<html></html>", {"s1": "<section></section>"})
    assert not r.passed
    assert "structure.no_visuals" in r.codes
    assert any("s1" in p and "blank" in p for p in r.problems)


def test_scene_with_only_an_image_is_not_flagged():
    plan = SimpleNamespace(windows=())
    frag = '<section><img src="shot.png" alt=""/></section>'
    r = st.scene_structure(None, plan, None, {"s1": frag})
    assert not any(c == "structure.no_visuals" for c in r.codes)


# --- zero duration --------------------------------------------------------


def test_scene_scheduled_for_zero_frames_is_flagged():
    window = SimpleNamespace(scene_id="s1", duration_frames=0)
    plan = SimpleNamespace(windows=(window,))
    r = st.scene_structure(None, plan, None, {})
    assert not r.passed
    assert "structure.zero_duration" in r.codes
    assert any("never appears" in p for p in r.problems)


def test_zero_length_animation_is_flagged():
    plan = SimpleNamespace(windows=())
    doc = '<div style="animation-duration:0ms">x</div>'
    r = st.scene_structure(None, plan, doc, {})
    assert "structure.zero_duration" in r.codes


# --- never visible --------------------------------------------------------


def test_word_sweep_with_no_word_spans_is_flagged():
    """The stat-hero bug class, caught on the artifact.

    The scene carries the motion class but the element it animates was never
    emitted, so the motion is accepted, rendered, and does nothing.
    """
    plan = SimpleNamespace(windows=())
    frag = '<section class="clip m-word-sweep"><h1 data-motion="word-sweep">Hi</h1></section>'
    r = st.scene_structure(None, plan, None, {"s1": frag})
    assert not r.passed
    assert "structure.never_visible" in r.codes
    assert any("no word span" in p for p in r.problems)


def test_word_sweep_with_word_spans_passes():
    plan = SimpleNamespace(windows=())
    frag = (
        '<section class="clip m-word-sweep"><h1 data-motion="word-sweep">'
        '<span class="word" style="animation-delay:0ms">Hi</span></h1></section>'
    )
    r = st.scene_structure(None, plan, None, {"s1": frag})
    assert "structure.never_visible" not in r.codes


def test_thinking_pulse_without_a_centerpiece_is_flagged():
    plan = SimpleNamespace(windows=())
    frag = '<section class="clip m-thinking-pulse"><h1>Hi</h1></section>'
    r = st.scene_structure(None, plan, None, {"s1": frag})
    assert "structure.never_visible" in r.codes
    assert any("no centerpiece" in p for p in r.problems)


def test_baseline_motion_needs_no_target():
    # fade-rise animates the .clip-motion wrapper, which every scene has by
    # construction, so requiring a target for it would be pure noise.
    plan = SimpleNamespace(windows=())
    frag = '<section class="clip m-fade-rise"><h1>Hi</h1></section>'
    r = st.scene_structure(None, plan, None, {"s1": frag})
    assert "structure.never_visible" not in r.codes


def test_unknown_motion_is_reported_not_assumed():
    """A motion with no declared target blocks rather than passing.

    We cannot say what it animates, so we cannot say it worked.
    """
    plan = SimpleNamespace(windows=())
    frag = '<section class="clip m-glitch-in"><h1>Hi</h1></section>'
    r = st.scene_structure(None, plan, None, {"s1": frag})
    assert "structure.never_visible" in r.codes
    assert any("no declared target" in p for p in r.problems)


def test_every_declared_motion_has_a_target_rule():
    """Keeps MOTION_TARGETS in sync with the grammar.

    Add a motion to the treatment grammar without saying what markup it
    animates and every scene using it would be flagged as unknown -- which is
    the correct outcome, but it should be caught here rather than in a run.
    """
    uncovered = set(MOTIONS) - set(st.MOTION_TARGETS) - {baseline_motion()}
    assert not uncovered, f"motion(s) {sorted(uncovered)} have no declared target"


def test_motion_targets_names_only_real_motions():
    ghosts = set(st.MOTION_TARGETS) - set(MOTIONS)
    assert not ghosts, f"MOTION_TARGETS names undeclared motion(s) {sorted(ghosts)}"


# --- transparent ----------------------------------------------------------


def test_keyframes_ending_fully_transparent_are_flagged():
    plan = SimpleNamespace(windows=())
    doc = "@keyframes fade-away{from{opacity:1}to{opacity:0}}"
    r = st.scene_structure(None, plan, doc, {})
    assert "structure.transparent" in r.codes
    assert any("ends at opacity 0" in p for p in r.problems)


def test_keyframes_ending_visible_pass():
    plan = SimpleNamespace(windows=())
    doc = "@keyframes colophon-in{from{opacity:0.85}to{opacity:1}}"
    r = st.scene_structure(None, plan, doc, {})
    assert "structure.transparent" not in r.codes


def test_percentage_syntax_is_also_checked():
    plan = SimpleNamespace(windows=())
    doc = "@keyframes f{0%{opacity:1}100%{opacity:0.0}}"
    r = st.scene_structure(None, plan, doc, {})
    assert "structure.transparent" in r.codes


# --- source error ---------------------------------------------------------


def test_missing_local_asset_is_flagged(tmp_path):
    plan = SimpleNamespace(windows=())
    doc = '<img src="shot.png"/>'
    r = st.scene_structure(None, plan, doc, {}, project_dir=tmp_path)
    assert "structure.source_error" in r.codes


def test_present_local_asset_passes(tmp_path):
    (tmp_path / "shot.png").write_bytes(b"")
    plan = SimpleNamespace(windows=())
    r = st.scene_structure(None, plan, '<img src="shot.png"/>', {},
                           project_dir=tmp_path)
    assert "structure.source_error" not in r.codes


def test_remote_and_data_assets_are_not_checked_against_disk(tmp_path):
    plan = SimpleNamespace(windows=())
    doc = '<img src="https://x/y.png"/><img src="data:image/png;base64,AAA"/>'
    r = st.scene_structure(None, plan, doc, {}, project_dir=tmp_path)
    assert "structure.source_error" not in r.codes


def test_missing_asset_is_skipped_without_a_project_dir():
    # Gate 14 runs before a render in cmd_qa; it must not fail for the want of
    # a directory it was never given.
    plan = SimpleNamespace(windows=())
    r = st.scene_structure(None, plan, '<img src="nope.png"/>', {})
    assert "structure.source_error" not in r.codes


# --- black frames ---------------------------------------------------------


def _plan_with_windows(*scene_ids: str):
    return SimpleNamespace(
        windows=tuple(
            SimpleNamespace(scene_id=sid, duration_frames=120, mid_s=2.0 + 6.0 * i)
            for i, sid in enumerate(scene_ids)
        )
    )


def _fake_luma(monkeypatch, readings):
    """Stand in for ffmpeg: (ymin, yavg, ymax) per scene, in order."""
    from colophon.review import extract as review_extract

    stats = [review_extract.LumaStats(lo, mid, hi) for lo, mid, hi in readings]
    calls = {}

    def fake(video, timestamps):
        calls["timestamps"] = list(timestamps)
        return stats

    monkeypatch.setattr(review_extract, "luma_stats_at", fake)
    return calls


def test_a_flat_frame_is_flagged(monkeypatch):
    """Spread 0 means every pixel is the same pixel: nothing was drawn."""
    _fake_luma(monkeypatch, [(26.0, 26.0, 26.0)])
    plan = _plan_with_windows("s1")
    frag = {"s1": '<section style="background:#0B0B12"><h1>Hi</h1></section>'}
    r = st.scene_structure(None, plan, None, frag, video_path="out.mp4")
    assert "structure.black_frame" in r.codes
    assert any("draws nothing" in p and "s1" in p for p in r.problems)


def test_a_frame_with_content_passes(monkeypatch):
    """The measured shape of a real scene: dark canvas, bright headline."""
    _fake_luma(monkeypatch, [(18.0, 27.6, 232.0)])
    plan = _plan_with_windows("s1")
    frag = {"s1": '<section style="background:#0B0B12"><h1>Hi</h1></section>'}
    r = st.scene_structure(None, plan, None, frag, video_path="out.mp4")
    assert "structure.black_frame" not in r.codes


def test_light_on_dark_and_dark_on_light_are_both_seen(monkeypatch):
    """Why spread and not peak: the departure can go either way.

    On a white canvas the content is *darker* than the background, so YMAX
    stays at 235 whether or not anything was drawn. Peak luma is blind to
    half the design space; spread is not.
    """
    blank_white = [(235.0, 235.0, 235.0)]
    drawn_white = [(16.0, 220.0, 235.0)]

    _fake_luma(monkeypatch, blank_white)
    plan = _plan_with_windows("s1")
    frag = {"s1": '<section style="background:#FFFFFF"><h1>Hi</h1></section>'}
    blank = st.scene_structure(None, plan, None, frag, video_path="out.mp4")
    assert "structure.black_frame" in blank.codes

    _fake_luma(monkeypatch, drawn_white)
    drawn = st.scene_structure(None, plan, None, frag, video_path="out.mp4")
    assert "structure.black_frame" not in drawn.codes


def test_the_message_names_the_background_it_is_flat_at(monkeypatch):
    """A blank frame that is flat at its declared background says so.

    'Flat at 26, which is #0B0B12' tells you the scene drew its background
    and nothing else. 'Flat at 26' alone leaves you guessing whether 26 was
    ever the intended colour.
    """
    _fake_luma(monkeypatch, [(26.0, 26.0, 26.0)])
    plan = _plan_with_windows("s1")
    frag = {"s1": '<section style="background:#0B0B12"><h1>Hi</h1></section>'}
    r = st.scene_structure(None, plan, None, frag, video_path="out.mp4")
    assert any("declared background" in p for p in r.problems)


def test_flat_at_an_unexpected_colour_does_not_blame_the_background(monkeypatch):
    _fake_luma(monkeypatch, [(16.0, 16.0, 16.0)])  # pure black, not #0B0B12
    plan = _plan_with_windows("s1")
    frag = {"s1": '<section style="background:#0B0B12"><h1>Hi</h1></section>'}
    r = st.scene_structure(None, plan, None, frag, video_path="out.mp4")
    assert "structure.black_frame" in r.codes
    assert not any("declared background" in p for p in r.problems)


def test_unmeasurable_video_is_silent_rather_than_blank(monkeypatch):
    """'Could not measure' must never be reported as 'measured and empty'."""
    from colophon.review import extract as review_extract

    def boom(video, timestamps):
        raise RuntimeError("ffmpeg is missing")

    monkeypatch.setattr(review_extract, "luma_stats_at", boom)
    plan = _plan_with_windows("s1")
    r = st.scene_structure(None, plan, None, {"s1": "<h1>Hi</h1>"},
                           video_path="out.mp4")
    assert "structure.black_frame" not in r.codes
    assert r.passed


def test_measurements_are_recorded_in_detail(monkeypatch):
    _fake_luma(monkeypatch, [(18.0, 27.6, 232.0)])
    plan = _plan_with_windows("s1")
    frag = {"s1": '<section style="background:#0B0B12"><h1>Hi</h1></section>'}
    r = st.scene_structure(None, plan, None, frag, video_path="out.mp4")
    assert r.detail["luma"][0]["spread"] == pytest.approx(214.0)
    assert r.detail["luma"][0]["scene"] == "s1"


def test_the_floor_sits_far_below_real_content():
    """Content measures 214-217; if the floor drifts near that, it is broken."""
    assert st.BLANK_SPREAD < 20.0
    assert st.BLANK_SPREAD > 0.0


# --- helpers --------------------------------------------------------------


def test_srgb_luma_is_on_the_ffmpeg_scale():
    """The helper must land on the scale we actually measure, not 0-255.

    Our encodes are yuv420p/color_range=tv, so sRGB 0-255 is rescaled to
    16-235 before it reaches signalstats. Each expectation below was verified
    against a solid-colour encode, not derived from the formula -- deriving
    them from the formula is how the original 0-255 version shipped.
    """
    assert st._srgb_luma("#000000") == pytest.approx(16.0, abs=0.5)
    assert st._srgb_luma("#FFFFFF") == pytest.approx(235.0, abs=0.5)
    assert st._srgb_luma("#0B0B12") == pytest.approx(26.0, abs=0.5)
    assert st._srgb_luma("#F5F5F7") == pytest.approx(227.0, abs=0.5)
    assert st._srgb_luma("#333333") == pytest.approx(60.0, abs=0.5)


def test_the_scale_is_not_the_naive_0_255_luma():
    """Pins the reason the helper exists, so nobody 'simplifies' it back.

    #0B0B12 has a relative luminance of 11.5, but ffmpeg reports 26 for it.
    A helper returning the naive value would sit ~14 units off every reading.
    """
    naive = 0.2126 * 0x0B + 0.7152 * 0x0B + 0.0722 * 0x12
    assert naive == pytest.approx(11.5, abs=0.1)
    assert st._srgb_luma("#0B0B12") == pytest.approx(26.0, abs=0.5)
    assert st._srgb_luma("#0B0B12") - naive > 10.0


def test_short_hex_is_expanded():
    assert st._srgb_luma("#fff") == pytest.approx(st._srgb_luma("#ffffff"))


def test_invalid_colour_returns_none():
    assert st._srgb_luma("not-a-colour") is None


def test_strip_tags_leaves_visible_text():
    assert st._strip_tags('<h1>Hello <span>world</span></h1>') == "Hello world"


def test_entities_are_stripped():
    assert st._strip_tags("<p>a&nbsp;b</p>") == "a b"


# --- taxonomy wiring ------------------------------------------------------


def test_every_code_the_gate_emits_is_registered():
    """An unregistered code blocks every run it touches, so catch it here."""
    source = Path(__file__).resolve().parents[1] / "colophon" / "qa" / "stages" / "structure.py"
    import re

    found = set(re.findall(r'"(structure\.[a-z_]+)"', source.read_text()))
    assert found, "no codes found in structure.py"
    assert found <= set(FAILURE_MODES), (
        f"unregistered: {sorted(found - set(FAILURE_MODES))}"
    )


def test_gate_carries_codes_positionally_with_problems():
    plan = SimpleNamespace(windows=())
    r = st.scene_structure(None, plan, "<html></html>", {"s1": "<section></section>"})
    assert len(r.codes) == len(r.problems)
    assert all(c is not None for c in r.codes)
