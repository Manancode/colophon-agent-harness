"""Grounding: a video must not show anything its claims do not license.

These run against the *emitted* fragment, not the spec. A spec can be perfectly
well-formed while the rendered output prints a number no claim contains, which
is why grounding is checked after emission (ADR 0005).
"""

from __future__ import annotations

import pytest

from colophon.content.grounding import (
    check_scene_grounding,
    element_text,
    visible_text,
)
from colophon.spec.schema import VideoSpec

from .conftest import scene, spec_dict


def _stat_spec() -> VideoSpec:
    """A proof scene whose claims actually contain a numeral."""
    return VideoSpec.from_dict(
        spec_dict(
            claims=[
                {
                    "claim_id": "t1",
                    "text": "Cut release time by 40%",
                    "kind": "title",
                    "source": "brief",
                },
                {
                    "claim_id": "n1",
                    "text": "Cut release time by 40% for your team.",
                    "kind": "narration",
                    "source": "brief",
                },
            ],
            scenes=[scene("s1", role="proof", treatment="stat-hero")],
        )
    )


class TestVisibleText:
    def test_strips_markup_and_collapses_whitespace(self):
        assert visible_text("<h1>  Hello   world </h1>") == "Hello world"

    def test_unescapes_entities(self):
        assert visible_text("<p>Tom &amp; Jerry</p>") == "Tom & Jerry"

    def test_ignores_comments_and_scripts(self):
        fragment = "<!-- draft --><script>var x=1;</script><p>Kept</p>"
        assert visible_text(fragment) == "Kept"

    def test_element_text_reads_the_first_matching_tag(self):
        assert element_text("<p>no</p><h1>yes</h1>", "h1") == "yes"

    def test_element_text_returns_none_when_absent(self):
        assert element_text("<p>only</p>", "h1") is None


class TestCleanFragment:
    def test_a_fragment_that_only_uses_bound_claims_is_clean(self):
        spec = _stat_spec()
        fragment = (
            '<h1 data-claim-id="t1">Cut release time by 40%</h1>'
            '<div class="figure">40%</div>'
            '<div class="caption">Cut release time by</div>'
            '<p data-claim-id="n1">Cut release time by 40% for your team.</p>'
        )
        assert check_scene_grounding(spec, spec.scenes[0], fragment) == []


class TestUnboundVisibleNumber:
    def test_a_number_no_claim_licenses_is_reported(self):
        spec = VideoSpec.from_dict(spec_dict())
        fragment = "<h1>Ship faster</h1><p>Cuts release time by 40%.</p>"
        problems = check_scene_grounding(spec, spec.scenes[0], fragment)
        assert any(p.rule == "unbound_visible_number" for p in problems)

    def test_the_report_names_the_offending_token(self):
        spec = VideoSpec.from_dict(spec_dict())
        fragment = "<h1>Ship faster</h1><p>Saves 12 hours a week.</p>"
        problems = check_scene_grounding(spec, spec.scenes[0], fragment)
        detail = " ".join(p.detail for p in problems)
        assert "12" in detail

    def test_a_licensed_number_is_accepted_even_when_displayed_huge(self):
        # stat-hero lifts the numeral out of the copy; it is still licensed
        spec = _stat_spec()
        fragment = (
            '<h1 data-claim-id="t1">Cut release time by 40%</h1>'
            '<div class="figure">40%</div>'
            '<p data-claim-id="n1">Cut release time by 40% for your team.</p>'
        )
        rules = {p.rule for p in check_scene_grounding(spec, spec.scenes[0], fragment)}
        assert "unbound_visible_number" not in rules


class TestTitleIntegrity:
    def test_a_rewritten_headline_is_fabrication(self):
        spec = _stat_spec()
        fragment = (
            '<h1 data-claim-id="t1">Cut Release Time By 40%</h1>'
            '<p data-claim-id="n1">Cut release time by 40% for your team.</p>'
        )
        problems = check_scene_grounding(spec, spec.scenes[0], fragment)
        assert any(p.rule == "title_mismatch" for p in problems)

    def test_whitespace_differences_are_tolerated(self):
        spec = _stat_spec()
        fragment = (
            '<h1 data-claim-id="t1">  Cut   release time by 40% </h1>'
            '<p data-claim-id="n1">Cut release time by 40% for your team.</p>'
        )
        rules = {p.rule for p in check_scene_grounding(spec, spec.scenes[0], fragment)}
        assert "title_mismatch" not in rules

    def test_a_missing_headline_is_reported(self):
        spec = _stat_spec()
        fragment = '<p data-claim-id="n1">Cut release time by 40% for your team.</p>'
        problems = check_scene_grounding(spec, spec.scenes[0], fragment)
        assert any(p.rule == "title_missing" for p in problems)


class TestNarrationSurvives:
    def test_dropping_a_clause_is_reported(self):
        spec = _stat_spec()
        # "for your team" silently omitted by the layout
        fragment = (
            '<h1 data-claim-id="t1">Cut release time by 40%</h1>'
            '<p data-claim-id="n1">Cut release time by 40%.</p>'
        )
        problems = check_scene_grounding(spec, spec.scenes[0], fragment)
        assert any(p.rule == "narration_clause_dropped" for p in problems)

    @pytest.mark.parametrize(
        "layout",
        [
            # the same narration, legitimately restructured by three treatments
            "rows",
            "columns",
            "command",
        ],
    )
    def test_legal_restructuring_keeps_every_word(self, layout: str):
        spec = _stat_spec()
        text = "Cut release time by 40% for your team."
        bodies = {
            "rows": f'<div class="row"><span>{text}</span></div>',
            "columns": f'<div class="col"><p>{text}</p></div>',
            "command": f'<div class="line"><span>{text}</span></div>',
        }
        fragment = f'<h1 data-claim-id="t1">Cut release time by 40%</h1>{bodies[layout]}'
        rules = {p.rule for p in check_scene_grounding(spec, spec.scenes[0], fragment)}
        assert "narration_clause_dropped" not in rules
