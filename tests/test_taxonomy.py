"""The closed-world taxonomy: what a finding does to a delivery.

The property these tests exist to protect is the fails-closed rule. A finding
the registry does not recognise must block. Every other behaviour is detail
next to that.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from colophon.qa import taxonomy as tx
from colophon.qa.runner import StageResult
from colophon.qa.taxonomy import Severity, assess, classify

REPO = Path(__file__).resolve().parents[1]
VALIDATE_SRC = REPO / "colophon" / "spec" / "validate.py"


def _result(
    stage_id: str,
    problems: list[str],
    codes: list[str | None] | None = None,
    advisory: bool = False,
) -> StageResult:
    return StageResult(
        stage_id=stage_id,
        passed=not problems,
        problems=problems,
        codes=codes or [],
        advisory=advisory,
    )


# --- registry integrity ---------------------------------------------------


def test_every_code_names_a_registered_stage():
    orphaned = {m.stage_id for m in tx.FAILURE_MODES.values()} - set(tx.STAGES)
    assert not orphaned


def test_code_literals_in_the_validator_are_all_registered():
    """Every code the validator can emit must exist in the taxonomy.

    Read from the source rather than from a set of fixtures: a fixture only
    proves the branches someone thought to write, while this proves the
    registry covers whatever the code actually says. An unregistered code
    would block every run it touched, so this is the test that keeps the
    taxonomy honest as the validator grows.
    """
    source = VALIDATE_SRC.read_text(encoding="utf-8")
    found = set(
        re.findall(
            r'"((?:spec|timeline|narrative|html|canvas|delivery)(?:\.[a-z0-9_]+)+)"',
            source,
        )
    )
    assert found, "no codes found in validate.py -- has the shape changed?"
    assert found <= set(tx.FAILURE_MODES), (
        f"codes emitted by validate.py are not in the taxonomy: "
        f"{sorted(found - set(tx.FAILURE_MODES))}"
    )


def test_no_duplicate_codes():
    # FAILURE_MODES is keyed by code, so a duplicate would silently drop one.
    # Recover the count from source to catch it.
    source = (REPO / "colophon" / "qa" / "taxonomy.py").read_text(encoding="utf-8")
    codes = re.findall(r'_mode\(\s*"([\w.]+)"', source)
    assert len(codes) == len(set(codes)), "duplicate _mode code(s) in the table"


def test_registry_stats_are_consistent():
    s = tx.stats()
    assert s.stages == len(tx.STAGES)
    assert s.codes == len(tx.FAILURE_MODES)
    assert 0 < s.stages_with_codes <= s.stages
    assert s.diagnostic_codes == sum(
        1 for m in tx.FAILURE_MODES.values() if m.severity is Severity.DIAGNOSTIC
    )


# --- the fails-closed rule ------------------------------------------------


def test_unknown_stage_blocks():
    finding = classify("gate_that_does_not_exist", "something new")
    assert finding.severity is Severity.BLOCKER
    assert finding.known is False


def test_unknown_code_blocks():
    finding = classify("spec_validate", "something new", "spec.nonexistent")
    assert finding.severity is Severity.BLOCKER
    assert finding.known is False


def test_known_blocker_code_is_known_and_blocks():
    finding = classify("spec_validate", "spec has no scenes", "spec.scenes.empty")
    assert finding.severity is Severity.BLOCKER
    assert finding.known is True


def test_known_diagnostic_code_warns():
    finding = classify("narrative_order", "no hook", "narrative.no_hook")
    assert finding.severity is Severity.DIAGNOSTIC
    assert finding.known is True


def test_unknown_stage_in_a_run_blocks_the_run():
    result = _result("mystery_gate", ["never seen before"])
    a = assess([result])
    assert a.state == "blocked"
    assert not a.shippable
    assert len(a.unknowns) == 1


def test_unknown_finding_is_reported_as_unknown_not_as_a_normal_blocker():
    result = _result("mystery_gate", ["never seen before"])
    a = assess([result])
    assert a.unknowns and all(f.known is False for f in a.unknowns)
    assert "not in the taxonomy" in str(a)


# --- stage-level fallback -------------------------------------------------


def test_uncoded_problem_falls_back_to_its_stage_default():
    # timeline_continuity is registered as blocking.
    finding = classify("timeline_continuity", "gap of 3 frame(s)")
    assert finding.severity is Severity.BLOCKER
    assert finding.known is True
    assert finding.code is None


def test_uncoded_problem_on_an_advisory_stage_warns():
    # narrative_order is registered as a diagnostic, so a stage that has not
    # been taught to emit codes still classifies correctly.
    finding = classify("narrative_order", "first scene has role 'cta'")
    assert finding.severity is Severity.DIAGNOSTIC


def test_a_code_beats_the_stage_default():
    # The advisory flag lives on the stage; severity lives on the problem.
    # Per-problem knowledge is strictly better than a whole-stage guess, so
    # an explicit code wins even against a blocking stage's default.
    finding = classify("static_html", "cosmetic nit", "narrative.no_hook")
    assert finding.severity is Severity.DIAGNOSTIC


# --- assessment states ----------------------------------------------------


def test_clean_run_is_ready():
    assert assess([_result("spec_validate", [])]).state == "ready"


def test_no_results_is_ready():
    assert assess([]).state == "ready"


def test_only_warnings_is_ready_with_warnings():
    a = assess([_result("narrative_order", ["no hook"], ["narrative.no_hook"], advisory=True)])
    assert a.state == "ready_with_warnings"
    assert a.shippable
    assert not a.blockers
    assert len(a.warnings) == 1


def test_any_blocker_blocks_even_alongside_warnings():
    a = assess(
        [
            _result("narrative_order", ["no hook"], ["narrative.no_hook"], advisory=True),
            _result("spec_validate", ["spec has no scenes"], ["spec.scenes.empty"]),
        ]
    )
    assert a.state == "blocked"
    assert len(a.blockers) == 1
    assert len(a.warnings) == 1


def test_codes_are_paired_with_problems_by_position():
    result = _result(
        "spec_validate",
        ["first problem", "second problem", "third problem"],
        ["spec.scenes.empty", "spec.claim.text"],
    )
    a = assess([result])
    # The tail has no code and falls back to the stage default (blocker).
    assert [f.code for f in a.blockers] == [
        "spec.scenes.empty",
        "spec.claim.text",
        None,
    ]


def test_assessment_serialises():
    a = assess([_result("spec_validate", ["spec has no scenes"], ["spec.scenes.empty"])])
    d = a.to_dict()
    assert d["state"] == "blocked"
    assert d["shippable"] is False
    assert d["taxonomy_version"] == tx.TAXONOMY_VERSION
    assert d["blockers"][0]["code"] == "spec.scenes.empty"
    assert d["blockers"][0]["known"] is True
    assert d["warnings"] == []


def test_assess_accepts_duck_typed_results():
    # It must not import the runner, or the two modules form a cycle.
    fake = SimpleNamespace(
        stage_id="narrative_order",
        problems=["no hook"],
        codes=["narrative.no_hook"],
    )
    assert assess([fake]).state == "ready_with_warnings"


def test_assess_tolerates_missing_codes_attribute():
    fake = SimpleNamespace(stage_id="spec_validate", problems=["boom"])
    a = assess([fake])
    assert a.state == "blocked"
    assert a.blockers[0].code is None


# --- coverage growth ------------------------------------------------------


def test_some_stages_are_not_yet_named_and_that_is_safe():
    """Documents the intended incomplete state.

    Not every stage emits codes yet. That is safe *only* because the fallback
    for an unnamed problem on a blocking stage is to block. If coverage ever
    reaches every stage, this test should be replaced, not deleted blindly --
    the property it guards is the fallback, not the incompleteness.
    """
    s = tx.stats()
    assert s.stages_with_codes < s.stages
    # and the fallback holds:
    assert classify("static_html", "unnamed problem").severity is Severity.BLOCKER


def test_taxonomy_version_is_pinned():
    assert tx.TAXONOMY_VERSION == "colophon-video-v1"


# --- display --------------------------------------------------------------


def test_stage_prefix_is_stripped_for_display_only():
    """Gates that prefix their own name shouldn't print it twice.

    The stored message keeps the prefix -- something may match on it -- so
    this asserts the display helper, not the finding.
    """
    from colophon.qa.taxonomy import _strip_stage_prefix

    assert _strip_stage_prefix("motion_accessibility: no query", "motion_accessibility") == (
        "no query"
    )
    assert _strip_stage_prefix("no query", "motion_accessibility") == "no query"
    assert _strip_stage_prefix("other_stage: x", "motion_accessibility") == "other_stage: x"

    finding = classify("motion_accessibility", "motion_accessibility: no query")
    assert finding.message == "motion_accessibility: no query"
    assert "motion_accessibility: motion_accessibility" not in str(
        assess([_result("motion_accessibility", ["motion_accessibility: no query"])])
    )


if __name__ == "__main__":
    pytest.main([__file__])
