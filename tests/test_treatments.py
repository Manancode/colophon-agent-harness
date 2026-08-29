"""The bounded treatment grammar: preconditions must actually block.

A precondition that warns instead of raising is decoration. ``stat-hero`` sets a
numeral huge, so if the bound claims contain no numeral the treatment would
have to invent one. These tests assert that it refuses.
"""

from __future__ import annotations

import pytest

from colophon.presentation.treatments import (
    TREATMENTS,
    baseline_for_role,
    build_context,
    treatment_ids,
    treatments_for_role,
    validate_treatment,
)
from colophon.spec.schema import ROLES


def _ctx(title: str | None, narration: str | None, scene=None):
    return build_context(scene=scene, title=title, narration=narration)


class TestGrammarShape:
    def test_every_role_has_exactly_two_treatments(self):
        for role in ROLES:
            assert len(treatments_for_role(role)) == 2, role

    def test_every_role_has_a_baseline(self):
        for role in ROLES:
            assert baseline_for_role(role), role

    def test_treatment_ids_are_all_reachable(self):
        assert len(treatment_ids()) == 12

    def test_treatment_ids_are_globally_unique(self):
        # TREATMENTS is keyed by treatment id, so two entries sharing an id
        # means the later one silently replaces the earlier one and a role
        # quietly loses a treatment. This regressed once with "statement-right".
        ids = [t.treatment_id for t in TREATMENTS.values()]
        assert len(ids) == len(set(ids))

    def test_rebuttal_right_is_distinct_from_statement_right(self):
        # the two right-aligned blocks are visually identical but must remain
        # separate grammar entries, one per role
        assert TREATMENTS["statement-right"].role == "problem"
        assert TREATMENTS["rebuttal-right"].role == "differentiator"


class TestStatHero:
    def test_blocked_when_no_claim_contains_a_numeral(self):
        ctx = _ctx("Faster releases", "Teams move quickly and safely.")
        with pytest.raises(ValueError, match="no numeral"):
            validate_treatment("proof", "stat-hero", ctx)

    def test_blocked_when_the_number_is_spelled_out(self):
        # "forty percent" licenses no digits, so rendering "40%" would be
        # fabrication. This is the case the Cadence brief documents.
        ctx = _ctx("Forty percent faster", "Forty percent faster releases.")
        with pytest.raises(ValueError, match="no numeral"):
            validate_treatment("proof", "stat-hero", ctx)

    def test_allowed_when_a_claim_contains_a_numeral(self):
        ctx = _ctx("40% faster releases", "Cut release time by 40%.")
        validate_treatment("proof", "stat-hero", ctx)


class TestCompareColumns:
    def test_blocked_without_a_contrast_cue(self):
        ctx = _ctx("Built for teams", "Every run is hashed and reproducible.")
        with pytest.raises(ValueError, match="contrast"):
            validate_treatment("differentiator", "compare-columns", ctx)

    def test_allowed_with_a_contrast_cue(self):
        ctx = _ctx("Built for speed instead of vanity metrics", "We ship instead of stalling.")
        validate_treatment("differentiator", "compare-columns", ctx)


class TestRowTreatments:
    def test_blocked_when_narration_has_one_clause(self):
        ctx = _ctx("Everything recorded", "Runs are hashed.")
        with pytest.raises(ValueError, match="clause"):
            validate_treatment("capability", "feature-rows", ctx)

    def test_allowed_when_narration_has_two_clauses(self):
        ctx = _ctx("Everything recorded", "Every run is hashed, every attempt is reproducible.")
        validate_treatment("capability", "feature-rows", ctx)

    def test_ui_frame_shares_the_precondition(self):
        ctx = _ctx("Everything recorded", "Runs are hashed.")
        with pytest.raises(ValueError):
            validate_treatment("capability", "ui-frame", ctx)


class TestRefusals:
    def test_unknown_treatment_raises(self):
        ctx = _ctx("Anything", "Anything.")
        with pytest.raises(ValueError, match="unknown treatment"):
            validate_treatment("hook", "hologram-hero", ctx)

    def test_treatment_from_the_wrong_role_raises(self):
        ctx = _ctx("Anything", "Anything.")
        with pytest.raises(ValueError, match="belongs to role"):
            validate_treatment("hook", "cta-command", ctx)

    def test_baselines_are_accepted_by_copy_that_satisfies_the_grammar(self):
        # A baseline is the *default* used when the treatment field is blank,
        # not an unconditional fallback. Copy that satisfies every precondition
        # in the grammar must therefore be accepted for every role.
        ctx = _ctx(
            "Cut 40% of release time",
            "Other tools show logs, but we rank fixes by hours saved.",
        )
        for role in ROLES:
            validate_treatment(role, baseline_for_role(role), ctx)

    def test_being_the_baseline_does_not_exempt_a_precondition(self):
        # feature-rows is the capability default, and a row treatment fed one
        # clause would have to invent rows. Defaulting to it must not silently
        # relax that: see resolve_treatment, which raises rather than
        # substituting when a requested treatment fails.
        ctx = _ctx("Everything recorded", "Runs are hashed.")
        with pytest.raises(ValueError, match="clause"):
            validate_treatment("capability", "feature-rows", ctx)
