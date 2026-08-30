"""The docs describe the gate set; this keeps them honest about it.

The README said "thirteen gates" long after a fourteenth had shipped, because
nothing connected the prose to the code. A doc that silently undercounts the
checks is worse than no doc — it tells you the system is stricter than it is.

The rule: the gate table is generated from the stage list, so adding a stage
forces the docs to be updated. It cannot check the *descriptions* are right,
only that every gate is present and the count is stated correctly.
"""

from __future__ import annotations

import re
from pathlib import Path

from colophon.harness.designer import _default_render_stages

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
UNDERSTAND = REPO / "docs" / "understand.md"
MAP = REPO / "docs" / "map.html"

#: Spelled-out numbers, so the prose can be checked against the stage list.
WORD_NUMBERS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
}


def _stage_ids() -> list[str]:
    return [fn.__name__ for fn in _default_render_stages()]


def test_the_gate_set_has_the_expected_shape():
    """Guard the total, so a change here has to be acknowledged in the docs."""
    ids = _stage_ids()
    assert len(ids) == 14, (
        f"gate count changed to {len(ids)}; update README.md, docs/understand.md "
        f"and this assertion together"
    )
    assert len(set(ids)) == len(ids), "a stage is listed twice"


def test_every_gate_appears_in_the_readme_table():
    readme = README.read_text()
    missing = [i for i in _stage_ids() if f"`{i}`" not in readme]
    assert not missing, f"gates missing from README.md: {missing}"


def test_every_gate_appears_in_the_plain_english_guide():
    guide = UNDERSTAND.read_text()
    missing = [i for i in _stage_ids() if f"`{i}`" not in guide]
    assert not missing, f"gates missing from docs/understand.md: {missing}"


def test_every_gate_appears_in_the_visual_map():
    page = MAP.read_text()
    missing = [i for i in _stage_ids() if f"<code>{i}</code>" not in page]
    assert not missing, f"gates missing from docs/map.html: {missing}"


def test_no_doc_claims_the_wrong_number_of_gates():
    """The specific drift that happened: the README said thirteen."""
    expected = len(_stage_ids())
    for path in (README, UNDERSTAND, MAP):
        text = path.read_text()
        for number, word in WORD_NUMBERS.items():
            if number == expected:
                continue
            pattern = rf"\b{word}\s+(?:deterministic\s+)?(?:QA\s+)?gates?\b"
            for m in re.finditer(pattern, text, re.IGNORECASE):
                raise AssertionError(
                    f"{path.name} says '{m.group(0)}' but there are {expected} gates"
                )


def test_the_readme_states_the_current_gate_count():
    readme = README.read_text()
    word = WORD_NUMBERS[len(_stage_ids())]
    assert re.search(rf"\b{word}\s+deterministic gates\b", readme, re.IGNORECASE), (
        f"README should describe the gate set as '{word} deterministic gates'"
    )


def test_the_plain_english_guide_exists_and_is_linked():
    assert UNDERSTAND.is_file()
    assert "docs/understand.md" in README.read_text()


def test_every_cli_command_is_documented():
    """A command nobody documented is a command nobody will find."""
    from colophon.cli import build_parser

    commands = {
        name
        for name, sub in build_parser()._subparsers._group_actions[0].choices.items()
    }
    guide = UNDERSTAND.read_text()
    undocumented = sorted(c for c in commands if f"`{c}`" not in guide)
    assert not undocumented, f"commands missing from docs/understand.md: {undocumented}"
