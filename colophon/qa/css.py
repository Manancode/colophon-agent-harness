"""Minimal CSS parsing shared by the artifact gates.

Deliberately not a real CSS parser. The gates need to answer narrow questions
about a stylesheet the emitter itself wrote, and every one of those questions
is about ``@keyframes``. A full parser would be a dependency and a failure
mode; thirty lines of brace counting is neither.

The one thing this gets right that a regex does not: **brace nesting**.

``@keyframes name { 0% { ... } 100% { ... } }``

The obvious regex, ``@keyframes\\s+([\\w-]+)\\s*\\{(.*?)\\}``, is non-greedy, so
it stops at the first closing brace it meets -- which is the end of the *first
step*, not the end of the block. That truncation is silent. A gate that reads
the body to find the opening keyframe still works by luck; one that looks for
the final step never fires at all.

That is not hypothetical: it is why the transparent-content check in
``structure.py`` reported nothing until this module existed.
"""

from __future__ import annotations

import re
from typing import Iterator, NamedTuple

_AT_RULE_RE = re.compile(r"@keyframes\s+([\w-]+)\s*\{")
_STEP_RE = re.compile(r"([^{}]*)\{([^{}]*)\}")


class Keyframes(NamedTuple):
    """One ``@keyframes`` block: its name and the steps it declares."""

    name: str
    steps: tuple[tuple[str, str], ...]  # ((selector, declarations), ...)

    @property
    def final_step(self) -> tuple[str, str] | None:
        """The step the animation rests on: ``to``/``100%``, else the last one.

        What the eye is left looking at when the animation finishes, which is
        what matters for whether content ends up visible.
        """
        if not self.steps:
            return None
        for selector, decls in reversed(self.steps):
            if re.fullmatch(r"\s*(?:100\s*%|to)\s*", selector):
                return selector, decls
        return self.steps[-1]


def keyframes_blocks(document: str) -> Iterator[Keyframes]:
    """Yield every @keyframes block with its body correctly brace-matched."""
    for match in _AT_RULE_RE.finditer(document):
        name = match.group(1)
        body, end = _match_braces(document, match.end() - 1)
        if body is None:
            continue
        yield Keyframes(
            name,
            tuple(
                (selector.strip(), decls.strip())
                for selector, decls in _STEP_RE.findall(body)
                if selector.strip()
            ),
        )
        del end  # brace matching is exact; there is nothing to resume from


def _match_braces(text: str, open_index: int) -> tuple[str | None, int]:
    """Body of the brace group starting at ``open_index`` (inclusive).

    Returns ``(None, ...)`` if the group is never closed, so truncated input
    is skipped rather than silently read to the end of the document.
    """
    if open_index >= len(text) or text[open_index] != "{":
        return None, open_index
    depth = 0
    i = open_index
    while i < len(text):
        char = text[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : i], i
        i += 1
    return None, i
