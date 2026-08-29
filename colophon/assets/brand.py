"""Brand tokens -> renderer theme contract.

The renderer adapter promises to expose every token in ``css_variables()`` as
a CSS custom property. That is the *entire* styling interface between spec and
renderer: treatments may only use these variables, never raw colours.

This is what makes a re-brand a spec edit rather than a code edit, and it is
also what lets the canvas audit hold — the background variable is the one
value the audit checks.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from ..spec.schema import Brand

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

#: Tokens the spec must supply.
REQUIRED = ("bg", "fg", "accent")

#: Tokens the renderer derives. Kept here so both sides agree on names.
DERIVED = (
    "muted",  # secondary text
    "hair",  # hairline rules
    "soft",  # faintest text
    "panel",  # card surface
    "bar",  # progress / divider fill
    "dot",  # list markers
    "accent_soft",  # tinted accent wash
    "accent_edge",  # accent hairline
)


class BrandError(ValueError):
    pass


def _parse_hex(value: str) -> tuple[int, int, int]:
    v = value.strip()
    if not _HEX_RE.match(v):
        raise BrandError(f"{value!r} is not a hex colour")
    body = v[1:]
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    return int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16)


def _rgba(value: str, alpha: float) -> str:
    r, g, b = _parse_hex(value)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _mix(a: str, b: str, t: float) -> str:
    ar, ag, ab = _parse_hex(a)
    br, bg, bb = _parse_hex(b)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


def css_variables(brand: Brand) -> dict[str, str]:
    """Full token set, required plus derived, as CSS custom property values."""
    tokens = dict(brand.tokens)
    missing = [t for t in REQUIRED if t not in tokens]
    if missing:
        raise BrandError(f"brand {brand.name!r} missing required token(s): {missing}")

    bg = tokens["bg"]
    fg = tokens["fg"]
    accent = tokens["accent"]

    derived = {
        "muted": _mix(fg, bg, 0.38),
        "soft": _mix(fg, bg, 0.55),
        "hair": _rgba(fg, 0.14),
        "panel": _rgba(fg, 0.05),
        "bar": _rgba(fg, 0.22),
        "dot": _rgba(accent, 0.85),
        "accent_soft": _rgba(accent, 0.14),
        "accent_edge": _rgba(accent, 0.42),
    }
    for key, value in derived.items():
        tokens.setdefault(key, value)

    return tokens


def to_css(brand: Brand, selector: str = ":root") -> str:
    """A ``:root { --bg: ...; }`` block for the renderer to inline."""
    tokens = css_variables(brand)
    decls = "".join(f"--{k}:{v};" for k, v in sorted(tokens.items()))
    return f"{selector}{{{decls}}}"
