"""Taste gates — deterministic checks against the AI-slop / generic-mean risk.

colophon's bet is a clean split: *geometry and structure* are checked by
machine (the other stages), and *taste* is set by a human reviewer. But a
large part of "taste" is actually a small, checkable vocabulary of things that
read as cheap — and those belong in the machine half. This module turns the
community's catalogued "AI video looks the same" tells into gates.

Grounded in RESEARCH-taste (2026-08-30), pulled via the context-dev MCP:
  - HN "The AI Aesthetic" thread (news.ycombinator.com/item?id=49117099)
  - Jim Nielsen, "The AI Aesthetic" (blog.jim-nielsen.com/2026/ai-aesthetic):
    sparkle ✨ = AI, shimmering "thinking" text, tiny icons.
  - The New Yorker / Kyle Chayka, "The A.I.-Design Aesthetic That's Taking
    Over the Internet": the mainstream catalogue of the same tells — beige and
    cream grounds, rusty orange accents, italicised serif emphasis, "tracked
    out" subheads, ticker-style text bars, and rounded rectangles with a neon
    glow. Four of those are checkable in emitted CSS; see below.
  - blakecrosley.com, "Motion Grammar": the closed duration band; the
    deletion test ("does it tell the user anything, or is it noise?").
  - Minimum-jerk motor control (Hogan 1984; Flash & Hogan 1985; Todorov &
    Jordan 1998): ease-in-out is not a convention but the trajectory that
    minimises the integral of squared jerk. That is why it reads as natural,
    and why a flat linear ramp reads as mechanical.
  - WCAG 2.3.1 (three flashes or below threshold) and 2.3.3 (animation from
    interactions): the accessibility floor that motion must respect.
  - Safavigerdini et al., "Generative AI Video Evaluation" (CVPRW 2026):
    existing benchmarks "prioritize aesthetic fidelity over cinematic camera
    motion and temporal causality", and the field is moving toward
    "trustworthy, agentic evaluation" — the niche these gates fill.

These gates are deliberately conservative. A tell only fires on a tight
signature (cream *and* orange together; a literal sparkle glyph in copy; a
glow blur over 24px), so the existing example specs — blue accents on
near-black or neutral-white — pass cleanly. Note that colophon's own
stylesheet letter-spaces its headings *negatively* (-.02em to -.05em); the
wide "tracked out" tell is scoped to headings only, so the legitimate .22em
tracking on the uppercase mono eyebrow does not trip it.
"""

from __future__ import annotations

import re
from typing import Any

from ...spec.schema import VideoSpec
from ..runner import StageResult

#: The clearest AI-styling glyphs. None of these belong in launch copy; their
#: presence is the single most-cited "this was made by a model" tell.
_SPARKLE_RE = re.compile(r"[✨🌈✺✷❋]")
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

#: CSS tells from the New Yorker catalogue that are checkable in the emitted
#: stylesheet. Each is deliberately narrow: colophon's own output declares no
#: box-shadow at all, no ticker, and *negatively* tracked headings, so none of
#: these fire on a healthy render.
_GLOW_RE = re.compile(r"box-shadow\s*:\s*([^;}]+)", re.I)
_TICKER_RE = re.compile(r"\b(?:ticker|marquee)\b", re.I)
_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_HEADING_RE = re.compile(r"\bh[123]\b")
_LS_RE = re.compile(r"letter-spacing\s*:\s*(-?[0-9.]+)em", re.I)
#: animation-duration may be a comma-separated list carrying one value per
#: animation in a shorthand chain (colophon itself emits "400ms,3s"), so every
#: value is parsed rather than just the first. Both units are handled: a
#: declaration like "1ms,4.0s" carries a real 1ms animation that the flicker
#: check must see.
_DUR_DECL_RE = re.compile(r"animation-duration\s*:\s*([^;}]+)", re.I)
_DUR_VAL_RE = re.compile(r"([0-9]*\.?[0-9]+)\s*(ms|s)\b", re.I)
_REDUCED_MOTION_RE = re.compile(r"prefers-reduced-motion", re.I)

#: A blur this wide is a "neon glow underneath for good measure", not a shadow.
_GLOW_BLUR_MIN_PX = 24
#: Positive heading tracking this wide is the "tracked out" subhead tell.
_TRACKED_OUT_EM = 0.15
#: Below this, repeated motion stops reading as motion and starts reading as
#: flicker — the WCAG 2.3.1 photosensitivity risk zone.
_FLASH_MS_MIN = 100


def _parse_hex(value: str | None) -> tuple[int, int, int] | None:
    v = (value or "").strip()
    if not _HEX_RE.match(v):
        return None
    body = v[1:]
    if len(body) == 3:
        body = "".join(c * 2 for c in body)
    return int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16)


def _brand_token(spec: VideoSpec, key: str) -> str | None:
    try:
        return spec.brand.tokens.get(key)
    except Exception:
        return None


def _is_cream(hexv: str | None) -> bool:
    """Warm near-white: light, with a clear warm tint (red leads blue).

    Neutral white (#F5F5F5, used by the probe specs) has R == G == B, so it is
    explicitly NOT cream — the warm offset is what separates "clinical" from
    "beige AI template".
    """
    rgb = _parse_hex(hexv)
    if not rgb:
        return False
    r, g, b = rgb
    if not (r > 225 and g > 215 and b > 195):
        return False
    if (r - b) < 10:  # neutral white, not cream
        return False
    if (g - b) < 2:
        return False
    return True


def _is_default_orange(hexv: str | None) -> bool:
    """The other half of the most-cited AI palette signature."""
    rgb = _parse_hex(hexv)
    if not rgb:
        return False
    r, g, b = rgb
    return r > 225 and 110 <= g <= 185 and b < 95


def _css_tells(document: str | None) -> list[str]:
    """Scan an emitted stylesheet for the CSS-checkable AI-styling tells.

    The New Yorker's designers named six visual habits. Four are expressible in
    CSS and therefore machine-checkable: the neon glow, the ticker bar, the
    tracked-out subhead, and (via the palette check) cream-plus-orange. The
    remaining two — italicised serif emphasis and desaturated mid-century hues
    — are legitimate choices in isolation and are left to human review.
    """
    tells: list[str] = []
    if not document:
        return tells

    for m in _GLOW_RE.finditer(document):
        px = [int(n) for n in re.findall(r"([0-9]+)px", m.group(1))]
        if px and max(px) >= _GLOW_BLUR_MIN_PX:
            tells.append(
                f"ai-slop tell: box-shadow blur {max(px)}px — the 'neon glow "
                f"underneath for good measure' dashboard idiom"
            )
            break

    if _TICKER_RE.search(document):
        tells.append(
            "ai-slop tell: ticker/marquee text bar present; the 'website as "
            "cable-news show' idiom is a named AI-design cliche"
        )

    for sel, body in _RULE_RE.findall(document):
        if not _HEADING_RE.search(sel):
            continue
        ls = _LS_RE.search(body)
        if ls and float(ls.group(1)) >= _TRACKED_OUT_EM:
            tells.append(
                f"ai-slop tell: heading tracked out to {ls.group(1)}em; wide "
                f"positive letter-spacing on subheads is a named AI-design tell"
            )
            break

    return tells


def _durations_ms(document: str) -> list[int]:
    """Every animation duration in the document, normalised to milliseconds.

    Zero is excluded on purpose: `animation-duration:0s` is how a stylesheet
    disables an animation, so it is the absence of motion rather than a flicker
    risk.
    """
    found: set[int] = set()
    for decl in _DUR_DECL_RE.finditer(document):
        for num, unit in _DUR_VAL_RE.findall(decl.group(1)):
            value = float(num)
            ms = int(value) if unit.lower() == "ms" else int(value * 1000)
            if ms > 0:
                found.add(ms)
    return sorted(found)


def ai_slop_detector(spec: VideoSpec, *, document: str | None = None, **_: Any) -> StageResult:
    """Refuse the generic-mean palette, glyph, and CSS tells.

    Three independent signatures, any of which fails the gate:
      1. cream/beige background AND default-orange accent — the exact pairing
         the HN/Reddit critiques call out as "every AI app looks the same".
      2. a sparkle/rainbow glyph in any bound claim's text.
      3. a CSS tell in the emitted stylesheet — a neon glow, a ticker bar, or
         a tracked-out heading (see _css_tells).
    """
    problems: list[str] = []

    bg = _brand_token(spec, "bg")
    accent = _brand_token(spec, "accent")
    if bg and accent and _is_cream(bg) and _is_default_orange(accent):
        problems.append(
            f"ai-slop palette: cream background {bg} with default-orange "
            f"accent {accent}; this exact pairing is the most-cited AI-video tell"
        )

    try:
        for claim in spec.claims:
            text = getattr(claim, "text", "") or ""
            if _SPARKLE_RE.search(text):
                cid = getattr(claim, "claim_id", "?")
                problems.append(
                    f"ai-slop tell: sparkle/rainbow glyph in claim {cid!r}; "
                    f"the ✨/🌈 idiom is the clearest signal of generic AI styling"
                )
    except Exception:
        pass

    problems.extend(_css_tells(document))

    return StageResult(
        stage_id="ai_slop_detector",
        passed=not problems,
        problems=problems,
        detail={"bg": bg, "accent": accent},
    )


def color_consistency(spec: VideoSpec, *, document: str | None = None, **_: Any) -> StageResult:
    """The emitted --accent must be the brand accent, not an off-brand hue.

    VBench lists "color" as a checkable dimension; canvas_audit already holds
    the background, this holds the accent. A treatment that quietly swaps in a
    different hue is a render defect, not a style choice — the brand is a spec
    token, and the renderer promised to expose exactly those tokens.
    """
    if not document:
        return StageResult(
            stage_id="color_consistency", passed=True, problems=[], advisory=True,
            detail={"skipped": "no emitted document to check"},
        )
    accent = _brand_token(spec, "accent")
    if not accent:
        return StageResult(
            stage_id="color_consistency", passed=True, problems=[],
            detail={"note": "no brand accent to compare against"},
        )
    m = re.search(r"--accent\s*:\s*([^;}\"']+)", document)
    emitted = m.group(1).strip() if m else None
    problems: list[str] = []
    if emitted is None:
        problems.append("emitted stylesheet declares no --accent token")
    else:
        a = _parse_hex(emitted)
        b = _parse_hex(accent)
        if a and b and a != b:
            problems.append(
                f"color_consistency: emitted --accent {emitted} != brand accent "
                f"{accent}; an off-brand hue leaked into the render"
            )
    return StageResult(
        stage_id="color_consistency", passed=not problems, problems=problems,
        detail={"emitted_accent": emitted, "brand_accent": accent},
    )


def centerpiece_invariant(
    spec: VideoSpec,
    *,
    document: str | None = None,
    scene_fragments: dict[str, str] | None = None,
    **_: Any,
) -> StageResult:
    """Exactly one motion centerpiece per scene; thinking-pulse must have one.

    This closes a real bug class the renderer comments describe: a CSS selector
    guess like ".figure, h1" once pulsed *two* elements on quote-card (the big
    glyph and the small attribution line) and read as a glitch. The renderer
    now stamps exactly one [data-centerpiece] per scene; this gate asserts it
    stayed that way. It is also the VBench "spatial relationship" / "scene"
    invariant expressed as a count.
    """
    if not document and not scene_fragments:
        return StageResult(
            stage_id="centerpiece_invariant", passed=True, problems=[], advisory=True,
            detail={"skipped": "no emitted output to check"},
        )

    problems: list[str] = []
    for scene in spec.scenes:
        frag = (scene_fragments or {}).get(scene.scene_id) or ""
        if not frag and document:
            m = re.search(
                r"<section[^>]*\bid=\"" + re.escape(scene.scene_id) + r"\"[^>]*>.*?</section>",
                document,
                re.S,
            )
            frag = m.group(0) if m else ""

        count = frag.count("data-centerpiece")
        if count == 0:
            problems.append(f"scene {scene.scene_id}: no motion centerpiece stamped")
        elif count > 1:
            problems.append(
                f"scene {scene.scene_id}: {count} centerpieces stamped; a motion "
                f"target must be unique or the pulse hits them all at once"
            )
        elif scene.motion == "thinking-pulse" and count != 1:
            problems.append(
                f"scene {scene.scene_id}: thinking-pulse requires exactly one "
                f"centerpiece to emphasize"
            )

    return StageResult(
        stage_id="centerpiece_invariant", passed=not problems, problems=problems,
        detail={"scenes_checked": len(spec.scenes)},
    )


def motion_accessibility(
    spec: VideoSpec,
    *,
    document: str | None = None,
    **_: Any,
) -> StageResult:
    """Motion must respect the accessibility floor: opt-out and no flicker.

    Two requirements, both deterministic:

      1. The stylesheet must honour prefers-reduced-motion. The Motion Grammar
         essay treats this as a first-class requirement rather than a nicety,
         and WCAG 2.3.3 (animation from interactions) is the standard behind
         it. colophon's own stylesheet disables every animation inside the
         media query; this gate asserts a renderer did not drop that block.
      2. No animation may run faster than _FLASH_MS_MIN. Motion repeated
         faster than roughly 100ms stops reading as motion and starts reading
         as flicker — the WCAG 2.3.1 photosensitivity hazard. That is a safety
         issue, not a taste issue, so it belongs on the machine side of the
         split rather than with the human reviewer.
    """
    if not document:
        return StageResult(
            stage_id="motion_accessibility", passed=True, problems=[], advisory=True,
            detail={"skipped": "no emitted document to check"},
        )

    problems: list[str] = []
    if not _REDUCED_MOTION_RE.search(document):
        problems.append(
            "motion_accessibility: no prefers-reduced-motion media query; "
            "motion cannot be opted out of by vestibular users (WCAG 2.3.3)"
        )

    durations = _durations_ms(document)
    fast = [d for d in durations if d < _FLASH_MS_MIN]
    if fast:
        problems.append(
            f"motion_accessibility: animation-duration {fast}ms is under the "
            f"{_FLASH_MS_MIN}ms floor; that is flicker rather than motion and "
            f"is a photosensitivity hazard (WCAG 2.3.1)"
        )

    return StageResult(
        stage_id="motion_accessibility", passed=not problems, problems=problems,
        detail={
            "reduced_motion": bool(_REDUCED_MOTION_RE.search(document)),
            "durations_ms": durations,
        },
    )
