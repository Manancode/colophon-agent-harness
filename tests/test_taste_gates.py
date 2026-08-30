"""Deterministic taste gates — the machine-checkable half of "good".

These assert the behaviours the RESEARCH-taste digest (2026-08-30) argued for:
the AI-slop palette/glyph tells, brand-color consistency, and exactly one
motion centerpiece per scene. Each gate must pass on a clean spec and fail on
a deliberately cheap one.
"""

from __future__ import annotations

from colophon.qa.stages import taste
from colophon.renderers.hyperframes.emit import render_document
from colophon.spec.schema import (
    Brand,
    Canvas,
    Claim,
    Scene,
    Timeline,
    VideoSpec,
)
from colophon.timeline.plan import build_plan


def _brand(tokens=None):
    base = {
        "accent": "#0A84FF",
        "bg": "#F5F5F5",
        "fg": "#0B0B0D",
        "muted": "#5A5A5F",
        "hair": "#E2E2E5",
    }
    if tokens:
        base.update(tokens)
    return Brand(name="Probe", tokens=base)


def _spec(brand=None, title_text="Build the agent that lives in chat", narration_text="Across 200 pilot repos."):
    return VideoSpec(
        spec_id="taste-probe",
        spec_version="0.1",
        title="taste probe",
        brand=brand or _brand(),
        canvas=Canvas(width=1920, height=1080, fps=30, background="#F5F5F5"),
        claims=[
            Claim(claim_id="c-title", kind="title", source="probe", text=title_text),
            Claim(claim_id="c-narr", kind="narration", source="probe", text=narration_text),
        ],
        scenes=[
            Scene(
                scene_id="s1",
                role="hook",
                treatment="hero-centered",
                motion="thinking-pulse",
                duration_s=3.0,
                title_claim_id="c-title",
                narration_claim_id="c-narr",
            )
        ],
        timeline=Timeline(policy="adjacent", transition="cut", transition_ms=0, overlap_s=0.0),
    )


def _doc(spec):
    return render_document(spec, build_plan(spec))


class TestAiSlopDetector:
    def test_clean_spec_passes(self):
        spec = _spec()
        doc = _doc(spec)
        r = taste.ai_slop_detector(spec, document=doc)
        assert r.passed and not r.problems

    def test_cream_orange_palette_fails(self):
        spec = _spec(brand=_brand({"bg": "#F5F0E8", "accent": "#FF8A3D"}))
        doc = _doc(spec)
        r = taste.ai_slop_detector(spec, document=doc)
        assert not r.passed
        assert any("cream" in p for p in r.problems)

    def test_neutral_white_is_not_cream(self):
        # #F5F5F5 (used by the probe specs) is neutral white, R==G==B, so it
        # must NOT trip the cream detector even with a blue accent.
        spec = _spec(brand=_brand({"bg": "#F5F5F5", "accent": "#0A84FF"}))
        doc = _doc(spec)
        assert taste.ai_slop_detector(spec, document=doc).passed

    def test_sparkle_in_claim_fails(self):
        spec = _spec(title_text="Ship it ✨ today")
        doc = _doc(spec)
        r = taste.ai_slop_detector(spec, document=doc)
        assert not r.passed
        assert any("sparkle" in p for p in r.problems)


class TestColorConsistency:
    def test_clean_passes(self):
        spec = _spec()
        doc = _doc(spec)
        assert taste.color_consistency(spec, document=doc).passed

    def test_offbrand_accent_fails(self):
        spec = _spec()
        doc = _doc(spec).replace("--accent:#0A84FF", "--accent:#FF0000")
        r = taste.color_consistency(spec, document=doc)
        assert not r.passed

    def test_no_document_is_advisory(self):
        r = taste.color_consistency(_spec())
        assert r.passed and r.advisory


class TestCenterpieceInvariant:
    def test_clean_passes(self):
        spec = _spec()
        doc = _doc(spec)
        assert taste.centerpiece_invariant(spec, document=doc).passed

    def test_zero_centerpiece_fails(self):
        spec = _spec()
        doc = _doc(spec).replace("data-centerpiece", "")
        r = taste.centerpiece_invariant(spec, document=doc)
        assert not r.passed

    def test_two_centerpieces_fails(self):
        spec = _spec()
        # double the markup occurrence (not the CSS selector) so the scene's
        # section ends up with two centerpieces
        doc = _doc(spec).replace("data-centerpiece style=", "data-centerpiece data-centerpiece style=", 1)
        r = taste.centerpiece_invariant(spec, document=doc)
        assert not r.passed


class TestPulseKeyframe:
    def test_reduced_motion_present(self):
        assert "prefers-reduced-motion" in _doc(_spec())

    def test_pulse_is_400ms_not_1200(self):
        doc = _doc(_spec())
        assert "animation-duration:400ms" in doc
        # only the explanatory comment may mention 1200ms; no animation uses it
        assert "animation-duration:1200ms" not in doc

    def test_pulse_has_anticipation_and_overshoot(self):
        doc = _doc(_spec())
        assert "scale(.92)" in doc and "scale(1.06)" in doc


class TestCssTells:
    """The New Yorker catalogue's machine-checkable half."""

    def test_neon_glow_fails(self):
        spec = _spec()
        doc = _doc(spec) + "<style>.card{box-shadow:0 0 32px rgba(255,138,61,.8)}</style>"
        r = taste.ai_slop_detector(spec, document=doc)
        assert not r.passed
        assert any("neon glow" in p for p in r.problems)

    def test_ordinary_shadow_passes(self):
        # A normal drop shadow is not the "neon glow underneath" idiom.
        spec = _spec()
        doc = _doc(spec) + "<style>.card{box-shadow:0 2px 12px rgba(0,0,0,.2)}</style>"
        assert taste.ai_slop_detector(spec, document=doc).passed

    def test_ticker_bar_fails(self):
        spec = _spec()
        doc = _doc(spec) + '<div class="ticker">BREAKING</div>'
        r = taste.ai_slop_detector(spec, document=doc)
        assert not r.passed
        assert any("ticker" in p for p in r.problems)

    def test_tracked_out_heading_fails(self):
        spec = _spec()
        doc = _doc(spec) + "<style>h2{letter-spacing:.22em}</style>"
        r = taste.ai_slop_detector(spec, document=doc)
        assert not r.passed
        assert any("tracked out" in p for p in r.problems)

    def test_negative_heading_tracking_passes(self):
        # colophon tightens its own headings (negative tracking). That is
        # optical fit, not the wide "tracked out" AI tell.
        spec = _spec()
        doc = _doc(spec)
        assert "letter-spacing:-" in doc
        assert taste.ai_slop_detector(spec, document=doc).passed

    def test_eyebrow_tracking_is_not_a_tell(self):
        # .eyebrow legitimately tracks to .22em, but it is a mono label rather
        # than a heading, so the tracked-out check must not fire on it.
        spec = _spec()
        doc = _doc(spec)
        assert "letter-spacing:.22em" in doc
        assert taste.ai_slop_detector(spec, document=doc).passed


class TestMotionAccessibility:
    def test_clean_passes(self):
        spec = _spec()
        doc = _doc(spec)
        r = taste.motion_accessibility(spec, document=doc)
        assert r.passed and not r.problems
        assert r.detail["reduced_motion"] is True

    def test_missing_reduced_motion_fails(self):
        spec = _spec()
        doc = _doc(spec).replace("prefers-reduced-motion", "prefers-contrast")
        r = taste.motion_accessibility(spec, document=doc)
        assert not r.passed
        assert any("prefers-reduced-motion" in p for p in r.problems)

    def test_sub_100ms_duration_is_flicker(self):
        spec = _spec()
        doc = _doc(spec) + "<style>.x{animation-duration:40ms}</style>"
        r = taste.motion_accessibility(spec, document=doc)
        assert not r.passed
        assert any("flicker" in p for p in r.problems)

    def test_multi_value_duration_list_is_fully_parsed(self):
        # "400ms,40ms" carries a real 40ms animation. colophon itself emits
        # this comma form, so parsing only the first value would miss it.
        doc = "<style>.x{animation-duration:400ms,40ms}</style>"
        assert taste._durations_ms(doc) == [40, 400]

    def test_seconds_are_converted(self):
        doc = "<style>.x{animation-duration:4.0s}</style>"
        assert taste._durations_ms(doc) == [4000]

    def test_zero_duration_is_not_flicker(self):
        # 0s is how a stylesheet disables motion, not a flicker risk.
        doc = "<style>.x{animation-duration:0s}</style>"
        assert taste._durations_ms(doc) == []

    def test_no_document_is_advisory(self):
        r = taste.motion_accessibility(_spec())
        assert r.passed and r.advisory
