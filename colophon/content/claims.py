"""Claim helpers.

A claim is the only legitimate source of visible copy. This module answers
one question: *what numbers and strings does this set of claims license?*
"""

from __future__ import annotations

import re
from typing import Iterable

from ..spec.schema import Claim, Scene, VideoSpec

#: Matches a number in rendered copy: 40, 4.99, 1,200, 30%, 2x, 2026.
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*%?")


def normalise_number(token: str) -> str:
    """Bring a numeric token to a comparable form: '1,200' -> '1200'."""
    return token.replace(",", "").replace(" ", "").rstrip("%").strip()


def numbers_in(text: str) -> set[str]:
    """Every numeric token in ``text``, normalised."""
    return {normalise_number(m.group(0)) for m in _NUMBER_RE.finditer(text or "")}


def numbers_of(claims: Iterable[Claim]) -> set[str]:
    """Every number the given claims license."""
    out: set[str] = set()
    for c in claims:
        out |= numbers_in(c.text)
    return out


def claims_for_scene(spec: VideoSpec, scene: Scene) -> list[Claim]:
    """The claims a scene is allowed to draw on. Nothing else is in scope."""
    out: list[Claim] = []
    for cid in (scene.title_claim_id, scene.narration_claim_id):
        claim = spec.claim(cid)
        if claim is not None:
            out.append(claim)
    return out


def licensed_strings(claims: Iterable[Claim]) -> set[str]:
    """Whitespace-normalised full claim texts."""
    return {" ".join(c.text.split()) for c in claims}


def has_contrast_cue(text: str) -> bool:
    """Does this copy set up a before/after or us/them comparison?

    Used as a treatment precondition. A treatment that splits the frame into
    two opposed columns needs copy that actually opposes something, otherwise
    the layout is decoration lying about the content.
    """
    lowered = (text or "").lower()
    cues = (
        " instead of",
        " rather than",
        " not ",
        " but ",
        " versus",
        " vs ",
        " other ",
        " others ",
        " most tools",
        " most teams",
        " unlike",
        " without ",
        " before ",
        " after ",
    )
    return any(cue in lowered for cue in cues)


def has_audience_cue(text: str) -> bool:
    """Does this copy say who it is for?"""
    lowered = (text or "").lower()
    cues = (
        " for ",
        "teams",
        "engineers",
        "developers",
        "you ",
        "your ",
        "founders",
        "designers",
        "marketers",
        "makers",
    )
    return any(cue in lowered for cue in cues)
