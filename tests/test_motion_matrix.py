"""A motion is only real if the renderer emits the element it targets.

This is the regression suite for the bug that motivated declaring motion
support on the treatment: ``stat-hero`` builds its own ``<h1 class="figure">``
and never calls ``_title()``, so ``word-sweep`` there emitted zero word spans.
The spec was accepted, the scene rendered, QA passed 7/7 — and the motion did
nothing at all.

That bug is worse than a wrong position, because it is *temporal*. A no-op
motion is pixel-identical to a finished one once the entrance settles, so no
contact sheet and no QA stage can see it. The only defence is to reject the
pair at spec time and to assert, for every pair the grammar claims, that the
renderer actually emits the element the motion animates.
"""

from __future__ import annotations

import re

import pytest

from colophon.presentation.treatments import (
    MOTIONS,
    TREATMENTS,
    baseline_motion,
    motion_ids,
    supported_motions,
)
from colophon.renderers.hyperframes.emit import render_document
from colophon.spec.schema import (
    ROLES,
    Brand,
    Canvas,
    Claim,
    Scene,
    Timeline,
    VideoSpec,
)
from colophon.spec.validate import validate
from colophon.timeline.plan import build_plan


def _spec(treatment: str, motion: str, role: str, title: str, narration: str) -> VideoSpec:
    return VideoSpec(
        spec_id=f"mx-{treatment}-{motion}",
        spec_version="0.1",
        title="motion matrix probe",
        brand=Brand(
            name="Matrix",
            tokens={
                "accent": "#0A84FF",
                "bg": "#F5F5F5",
                "fg": "#0B0B0D",
                "muted": "#5A5A5F",
                "hair": "#E2E2E5",
            },
        ),
        canvas=Canvas(width=1920, height=1080, fps=30, background="#F5F5F5"),
        claims=[
            Claim(claim_id="c-title", kind="title", source="probe", text=title),
            Claim(claim_id="c-narr", kind="narration", source="probe", text=narration),
        ],
        scenes=[
            Scene(
                scene_id="s1",
                role=role,
                treatment=treatment,
                motion=motion,
                duration_s=3.0,
                title_claim_id="c-title",
                narration_claim_id="c-narr",
            )
        ],
        timeline=Timeline(
            policy="adjacent", transition="cut", transition_ms=0, overlap_s=0.0
        ),
    )


def _body_html(spec: VideoSpec) -> str:
    """The document with its stylesheet stripped.

    The stylesheet contains the ``[data-centerpiece]`` selector, so counting
    occurrences without stripping it would count the selector as an element.
    """
    html = render_document(spec, build_plan(spec))
    return re.sub(r"<style>.*?</style>", "", html, flags=re.S)


ROLE_OF = {t.treatment_id: t.role for t in TREATMENTS.values()}
TITLE_FOR = {"stat-hero": "40%"}


def _title_for(treatment: str) -> str:
    return TITLE_FOR.get(treatment, "Create an agent that lives in chats")


ALL_PAIRS = [
    (tid, m) for tid in sorted(TREATMENTS) for m in supported_motions(tid)
]


class TestDeclaredSupport:
    def test_every_declared_motion_exists(self):
        for tid, treatment in TREATMENTS.items():
            for m in treatment.motions:
                assert m in MOTIONS, f"{tid} declares unknown motion {m}"

    def test_baseline_is_supported_everywhere(self):
        # fade-rise animates the .clip-motion wrapper, so it applies to every
        # treatment regardless of what markup the treatment emits.
        base = baseline_motion()
        for tid in TREATMENTS:
            assert base in supported_motions(tid), tid

    def test_no_motion_is_orphaned(self):
        # A motion no treatment supports is dead vocabulary: an agent could
        # select it and it would render as a no-op.
        reachable = {m for _, m in ALL_PAIRS}
        assert reachable == set(MOTIONS), f"orphaned: {set(MOTIONS) - reachable}"

    def test_supported_motions_lists_baseline_first(self):
        for tid in TREATMENTS:
            assert supported_motions(tid)[0] == baseline_motion(), tid


class TestUnsupportedPairsAreRejected:
    @pytest.mark.parametrize(
        "treatment,motion",
        [
            # stat-hero builds its own <h1 class="figure"> and never calls
            # _title(), so the word spans were never emitted.
            ("stat-hero", "word-sweep"),
            # quote-card's title is the small attribution line; the quote
            # itself is the narration. Sweeping would animate the one element
            # nobody looks at.
            ("quote-card", "word-sweep"),
        ],
    )
    def test_pair_is_rejected(self, treatment, motion):
        spec = _spec(
            treatment,
            motion,
            ROLE_OF[treatment],
            _title_for(treatment),
            "Across 200 pilot repositories.",
        )
        problems = validate(spec)
        assert any("does not support motion" in p for p in problems), problems

    def test_unknown_motion_still_reports_the_vocabulary(self):
        spec = _spec(
            "hero-centered", "not-a-motion", "hook", "Hello there", "Supporting line."
        )
        problems = validate(spec)
        assert any("not in" in p for p in problems), problems


class TestSupportedPairsActuallyRender:
    """The load-bearing test: every claimed pair must emit real motion markup."""

    @pytest.mark.parametrize("treatment,motion", ALL_PAIRS)
    def test_exactly_one_centerpiece(self, treatment, motion):
        spec = _spec(
            treatment,
            motion,
            ROLE_OF[treatment],
            _title_for(treatment),
            "Across 200 pilot repositories.",
        )
        body = _body_html(spec)
        assert body.count("data-centerpiece") == 1, (
            f"{treatment}+{motion} emitted "
            f"{body.count('data-centerpiece')} centerpiece elements"
        )

    @pytest.mark.parametrize(
        "treatment,motion",
        [(t, m) for (t, m) in ALL_PAIRS if m == "word-sweep"],
    )
    def test_word_sweep_emits_word_spans(self, treatment, motion):
        """A word-sweep with zero spans is a silent no-op. This is the bug."""
        spec = _spec(
            treatment,
            motion,
            ROLE_OF[treatment],
            _title_for(treatment),
            "Across 200 pilot repositories.",
        )
        body = _body_html(spec)
        spans = body.count('<span class="word"')
        assert spans > 0, f"{treatment}+{motion} emitted no word spans (no-op)"
        # and the sweep must be staggered, not simultaneous
        delays = re.findall(r"animation-delay:(\d+)ms", body)
        assert len(set(delays)) == spans, (
            f"{treatment}+{motion}: {spans} spans but delays {sorted(set(delays))}"
        )

    @pytest.mark.parametrize(
        "treatment,motion",
        [(t, m) for (t, m) in ALL_PAIRS if m == "thinking-pulse"],
    )
    def test_thinking_pulse_targets_the_centerpiece(self, treatment, motion):
        spec = _spec(
            treatment,
            motion,
            ROLE_OF[treatment],
            _title_for(treatment),
            "Across 200 pilot repositories.",
        )
        body = _body_html(spec)
        # the marker must sit ON an element, not float in the stylesheet
        assert re.search(r"<[a-z0-9]+[^>]*\sdata-centerpiece[\s>]", body), (
            f"{treatment}+{motion}: centerpiece marker is not on an element"
        )

    def test_all_pairs_are_covered(self):
        # guards against the parametrised lists silently going empty
        assert len(ALL_PAIRS) >= len(TREATMENTS)
        assert any(m == "word-sweep" for _, m in ALL_PAIRS)
        assert any(m == "thinking-pulse" for _, m in ALL_PAIRS)


class TestGrammarIntegrity:
    def test_motion_ids_are_sorted_and_unique(self):
        ids = motion_ids()
        assert list(ids) == sorted(set(ids))

    def test_every_role_still_has_two_treatments(self):
        for role in ROLES:
            assert len([t for t in TREATMENTS.values() if t.role == role]) == 2, role
