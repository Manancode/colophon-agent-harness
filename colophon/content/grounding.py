"""Grounding checks — the rules that stop a video from inventing things.

These run against the *rendered* output, not the spec. A treatment can look
perfectly innocent in the spec and still emit a number that no claim licenses,
so grounding has to be verified after emission, on the actual DOM.

The two rules that have caught real defects:

``unbound_visible_number``
    Every number visible in the output must appear in a claim bound to that
    scene. This is why a claim reading "forty percent" blocks a treatment
    that renders "40%" — the digits are not in the claim.

``title_mismatch``
    The visible headline must be byte-identical (modulo whitespace) to its
    bound claim. A treatment that trims, title-cases or "improves" a headline
    has changed a claim, which is fabrication.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass
from typing import Iterable

from ..spec.schema import Claim, Scene, VideoSpec
from .claims import numbers_in, normalise_number

_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class GroundingProblem:
    scene_id: str
    rule: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"scene_id": self.scene_id, "rule": self.rule, "detail": self.detail}

    def __str__(self) -> str:
        return f"[{self.rule}] {self.scene_id}: {self.detail}"


def visible_text(fragment: str) -> str:
    """Strip markup down to the text a viewer would actually read."""
    out = _COMMENT_RE.sub(" ", fragment or "")
    out = _SCRIPT_RE.sub(" ", out)
    out = _TAG_RE.sub(" ", out)
    out = _html.unescape(out)
    return _WS_RE.sub(" ", out).strip()


def element_text(fragment: str, tag: str = "h1") -> str | None:
    """Text of the first ``<tag ...>...</tag>`` in the fragment."""
    m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", fragment or "", re.S | re.I)
    return visible_text(m.group(1)) if m else None


def check_scene_grounding(
    spec: VideoSpec, scene: Scene, fragment: str
) -> list[GroundingProblem]:
    """Grounding rules for one scene's rendered fragment."""
    problems: list[GroundingProblem] = []
    sid = scene.scene_id

    claims = [c for c in (spec.claim(scene.title_claim_id), spec.claim(scene.narration_claim_id)) if c]
    licensed: set[str] = set()
    for c in claims:
        licensed |= numbers_in(c.text)

    rendered = visible_text(fragment)
    for token in sorted(numbers_in(rendered)):
        if token not in licensed:
            problems.append(
                GroundingProblem(
                    sid,
                    "unbound_visible_number",
                    f"renders {token!r} but no bound claim contains it "
                    f"(licensed: {sorted(licensed) or 'none'})",
                )
            )

    title_claim = spec.claim(scene.title_claim_id)
    if title_claim is not None:
        shown = element_text(fragment, "h1")
        if shown is None:
            problems.append(
                GroundingProblem(sid, "title_missing", "no <h1> found for the title claim")
            )
        else:
            expected = " ".join(title_claim.text.split())
            if shown != expected:
                problems.append(
                    GroundingProblem(
                        sid,
                        "title_mismatch",
                        f"visible title {shown!r} != claim {title_claim.claim_id} {expected!r}",
                    )
                )

    narration_claim = spec.claim(scene.narration_claim_id)
    if narration_claim is not None and claims:
        # every word of the narration must survive somewhere in the fragment;
        # a treatment that silently drops a clause is dropping a claim.
        expected_words = _content_words(narration_claim.text)
        rendered_words = set(_content_words(rendered))
        missing = [w for w in expected_words if w not in rendered_words]
        if missing:
            problems.append(
                GroundingProblem(
                    sid,
                    "narration_clause_dropped",
                    f"narration words missing from output: {missing[:8]}",
                )
            )

    return problems


_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "you",
        "your",
        "with",
    }
)


def _content_words(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 2]
