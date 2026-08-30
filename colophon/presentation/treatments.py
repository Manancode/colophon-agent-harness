"""The bounded treatment grammar.

Two intentional treatments per role, twelve in total. Bounded on purpose:
an unbounded treatment space is how you get random variation that games a
score instead of meaning something.

Each treatment declares preconditions. A precondition is not decoration — it
is the grammar refusing to lie. ``stat-hero`` lifts a numeral out of the copy
and sets it huge, so it is blocked unless the bound claims actually contain a
numeral. ``compare-columns`` splits the frame into two opposed columns, so it
is blocked unless the copy contains a contrast cue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from ..content.claims import has_contrast_cue, numbers_in
from ..spec.schema import ROLES

#: Precondition context keys: scene, title, narration, numbers, combined
Precondition = Callable[[Mapping[str, Any]], tuple[bool, str]]


def _always(_ctx: Mapping[str, Any]) -> tuple[bool, str]:
    return True, ""


def _has_number(ctx: Mapping[str, Any]) -> tuple[bool, str]:
    numbers = ctx.get("numbers") or set()
    if numbers:
        return True, ""
    return (
        False,
        "no numeral in the bound claims; a stat treatment would have to invent one",
    )


def _has_contrast(ctx: Mapping[str, Any]) -> tuple[bool, str]:
    text = ctx.get("combined") or ""
    if has_contrast_cue(text):
        return True, ""
    return (
        False,
        "no contrast cue in the copy; opposing columns would imply a comparison "
        "the narration does not make",
    )


def _has_multiple_clauses(ctx: Mapping[str, Any]) -> tuple[bool, str]:
    text = ctx.get("narration") or ""
    parts = [p.strip() for p in _split_clauses(text) if p.strip()]
    if len(parts) >= 2:
        return True, ""
    return (
        False,
        f"narration yields {len(parts)} clause(s); a row treatment needs at least 2 "
        "or it would have to invent rows",
    )


def _has_audience(ctx: Mapping[str, Any]) -> tuple[bool, str]:
    text = (ctx.get("combined") or "").lower()
    cues = (" for ", "teams", "engineers", "developers", "you", "your", "founders")
    if any(c in text for c in cues):
        return True, ""
    return False, "no audience cue in the copy"


def _split_clauses(text: str) -> list[str]:
    import re

    parts = re.split(r",\s*|\s+and\s+", text or "")
    return [p for p in parts if p and p.strip()]


@dataclass(frozen=True)
class Treatment:
    treatment_id: str
    role: str
    description: str
    preconditions: tuple[Precondition, ...] = ()
    baseline: bool = False
    #: structural family, used by the renderer to pick a CSS strategy
    family: str = "statement"
    #: Non-baseline motions this treatment can actually carry. The baseline
    #: motion is universal *by construction* — it lives on the .clip-motion
    #: wrapper, not on treatment-specific markup — so it is never listed here.
    #:
    #: This field exists because a motion is only real if the renderer emits
    #: the element it targets. stat-hero builds its own <h1 class="figure">
    #: and never calls _title(), so word-sweep there emitted zero word spans:
    #: a silent no-op that passed every QA stage, because a motion that never
    #: runs looks identical to one that finished once the entrance settles.
    #: Declaring support and validating the pair turns that class of bug from
    #: invisible into a spec error.
    motions: tuple[str, ...] = ()


def _t(
    tid: str,
    role: str,
    desc: str,
    *pre: Precondition,
    family: str = "statement",
    motions: tuple[str, ...] = (),
) -> Treatment:
    return Treatment(tid, role, desc, pre, family=family, motions=motions)


_TREATMENT_TABLE: tuple[Treatment, ...] = (
        # ---- hook -------------------------------------------------------
        Treatment(
            "hero-centered",
            "hook",
            "Centred wordmark with a single supporting line below.",
            baseline=True,
            family="hero",
            motions=("word-sweep", "thinking-pulse"),
        ),
        _t(
            "hero-split",
            "hook",
            "Wordmark left, supporting line right, divided by a hairline.",
            family="split",
            motions=("word-sweep", "thinking-pulse"),
        ),
        # ---- problem ----------------------------------------------------
        Treatment(
            "statement-left",
            "problem",
            "Headline anchored to a vertical rule, body beneath.",
            baseline=True,
            family="statement",
            motions=("word-sweep", "thinking-pulse"),
        ),
        _t(
            "statement-right",
            "problem",
            "Same block mirrored to the right edge.",
            family="statement",
            motions=("word-sweep", "thinking-pulse"),
        ),
        # ---- capability -------------------------------------------------
        Treatment(
            "feature-rows",
            "capability",
            "Narration split into stacked rows, each with a marker.",
            (_has_multiple_clauses,),
            baseline=True,
            family="rows",
            motions=("word-sweep", "thinking-pulse"),
        ),
        _t(
            "ui-frame",
            "capability",
            "Rows inside a windowed card with browser chrome.",
            _has_multiple_clauses,
            family="frame",
            motions=("word-sweep", "thinking-pulse"),
        ),
        # ---- differentiator ---------------------------------------------
        # NOTE: this looks identical to the problem role's "statement-right",
        # but it must not share the id. TREATMENTS is keyed by treatment_id, so
        # two entries with the same id means the later one silently replaces the
        # earlier one and a role quietly loses a treatment. Ids are global.
        Treatment(
            "rebuttal-right",
            "differentiator",
            "Headline block mirrored right; single-column rebuttal.",
            baseline=True,
            family="statement",
            motions=("word-sweep", "thinking-pulse"),
        ),
        _t(
            "compare-columns",
            "differentiator",
            "Two opposed columns split from the narration's contrast.",
            _has_contrast,
            family="columns",
            motions=("word-sweep", "thinking-pulse"),
        ),
        # ---- proof ------------------------------------------------------
        # word-sweep is deliberately NOT supported here. The quote itself is
        # the narration (a <blockquote>), while _title() only renders the
        # attribution line in .attr. Sweeping would animate the small source
        # line and leave the actual quote static — the motion would land on
        # the one element nobody is looking at.
        Treatment(
            "quote-card",
            "proof",
            "Large quote glyph, the quote, a hairline, then a source line.",
            baseline=True,
            family="quote",
            motions=("thinking-pulse",),
        ),
        # word-sweep is deliberately NOT supported here, and this is the bug
        # that motivated the whole field: stat-hero builds its own
        # <h1 class="figure"> and never calls _title(), so the word spans were
        # never emitted. The motion was accepted, rendered, and did nothing —
        # and no QA stage could tell, because a no-op motion is
        # indistinguishable from a finished one once the entrance settles.
        _t(
            "stat-hero",
            "proof",
            "The numeral set huge, with the remainder as a caption.",
            _has_number,
            family="stat",
            motions=("thinking-pulse",),
        ),
        # ---- cta --------------------------------------------------------
        Treatment(
            "cta-command",
            "cta",
            "Terminal-like stacked lines ending in a URL pill.",
            baseline=True,
            family="command",
            motions=("word-sweep", "thinking-pulse"),
        ),
        _t(
            "cta-panel",
            "cta",
            "Single centred panel with the action and the URL.",
            family="panel",
            motions=("word-sweep", "thinking-pulse"),
        ),
)

TREATMENTS: dict[str, Treatment] = {t.treatment_id: t for t in _TREATMENT_TABLE}


def treatments_for_role(role: str) -> tuple[Treatment, ...]:
    return tuple(t for t in TREATMENTS.values() if t.role == role)


def baseline_for_role(role: str) -> str | None:
    for t in treatments_for_role(role):
        if t.baseline:
            return t.treatment_id
    return None


# --------------------------------------------------------------------------
# Motion primitives
# --------------------------------------------------------------------------
#
# A motion is the *entrance* — what the eye sees as the scene comes in. It is
# separate from treatment, which is the *layout* — where the copy sits. A
# scene composes both: hero-centered (layout) over word-sweep (motion).
#
# The boundary is deliberate: animations drive discrete preset channels
# (opacity, transform, per-word delay) rather than CSS keyframes spread
# across the stylesheet. Treating motion as data means a planner can
# pick the entrance from a closed vocabulary and the renderer can validate it.
#
# Two motions to start. ``fade-rise`` is the baseline: the whole scene body
# fades up and translates into place. ``word-sweep`` is the new one: the title
# words settle in sequence, one stagger per word, transform only — no opacity
# on the children, because opacity is already animating on the parent and
# stacking fractional opacities drops the whole subtree (the bug that forced
# the colophon-hold workaround in the original emitter).


@dataclass(frozen=True)
class Motion:
    motion_id: str
    description: str
    baseline: bool = False


_MOTION_TABLE: tuple[Motion, ...] = (
    Motion(
        "fade-rise",
        "The whole scene body fades up (opacity 0.85->1) and translates "
        "into place (translateY 14px->0). One CSS keyframe per scene.",
        baseline=True,
    ),
    Motion(
        "word-sweep",
        "The title's words settle in sequence, one stagger per word, "
        "transform only (translateY 8px->0). No opacity on the words — the "
        "scene body's fade handles that, and stacking fractional opacities "
        "drops the subtree.",
    ),
    Motion(
        "thinking-pulse",
        "The scene's single centerpiece ([data-centerpiece]: .figure, .glyph, "
        "or h1) does one weighted pulse over 400ms — Anticipation (a slight "
        "wind-up dip to .92), Strike (overshoot to 1.06), Settle (.97) to "
        "Rest. The 400ms total sits inside the Motion Grammar closed band "
        "(page/modal ~300-400ms); the weight comes from the dip and overshoot, "
        "not from scale or duration, and it is transform-only (no opacity) for "
        "the subtree-drop reason shared with word-sweep. Used for 'agent is "
        "initializing' beats, single-stat emphases, and quote-glyph reveals.",
    ),
)

MOTIONS: dict[str, Motion] = {m.motion_id: m for m in _MOTION_TABLE}


def motion_ids() -> tuple[str, ...]:
    return tuple(sorted(MOTIONS))


def baseline_motion() -> str:
    for m in _MOTION_TABLE:
        if m.baseline:
            return m.motion_id
    raise ValueError("no baseline motion declared")


def _check_motion_grammar() -> None:
    ids = [m.motion_id for m in _MOTION_TABLE]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate motion id(s) {duplicates}")
    if not any(m.baseline for m in _MOTION_TABLE):
        raise ValueError("no baseline motion declared")
    if sum(1 for m in _MOTION_TABLE if m.baseline) > 1:
        raise ValueError("more than one baseline motion declared")


_check_motion_grammar()


def validate_motion(motion: str) -> None:
    if motion not in MOTIONS:
        raise ValueError(
            f"unknown motion {motion!r}; valid: {', '.join(motion_ids())}"
        )


def supported_motions(treatment_id: str) -> tuple[str, ...]:
    """The motions a treatment can actually carry, baseline first.

    The baseline is prepended rather than declared because it is universal by
    construction: ``fade-rise`` animates the ``.clip-motion`` wrapper, so it
    applies to every treatment regardless of what markup the treatment emits.
    """
    t = TREATMENTS[treatment_id]
    base = baseline_motion()
    extra = tuple(m for m in t.motions if m != base)
    return (base,) + extra


def _check_treatment_motions() -> None:
    """Every declared motion must exist, and every motion must be reachable.

    The second half is the one that earns its keep: a motion nobody supports is
    dead vocabulary in the grammar. It would show up in the spec's error text
    and in whatever planner we build later, and an agent would happily select
    it, only for it to render as a no-op.
    """
    known = set(MOTIONS)
    for t in _TREATMENT_TABLE:
        unknown = sorted(set(t.motions) - known)
        if unknown:
            raise ValueError(
                f"treatment {t.treatment_id!r} declares unknown motion(s) {unknown}"
            )
        dupes = sorted({m for m in t.motions if t.motions.count(m) > 1})
        if dupes:
            raise ValueError(
                f"treatment {t.treatment_id!r} declares duplicate motion(s) {dupes}"
            )

    reachable = {m for t in _TREATMENT_TABLE for m in supported_motions(t.treatment_id)}
    orphaned = sorted(known - reachable)
    if orphaned:
        raise ValueError(f"motion(s) {orphaned} are supported by no treatment")


_check_treatment_motions()


# --------------------------------------------------------------------------
# Motion primitives
# --------------------------------------------------------------------------
#
# A motion is the *entrance* — what the eye sees as the scene comes in. It is
# separate from treatment, which is the *layout* — where the copy sits. A
# scene composes both: hero-centered (layout) over word-sweep (motion).
#
# The boundary is deliberate: animations drive discrete preset channels
# (opacity, transform, per-word delay) rather than CSS keyframes spread
# across the stylesheet. Treating motion as data means a planner can
# pick the entrance from a closed vocabulary and the renderer can validate it.
#
# Two motions to start. ``fade-rise`` is the baseline: the whole scene body
# fades up and translates into place. ``word-sweep`` is the new one: the title
# words settle in sequence, one stagger per word, transform only — no opacity
# on the children, because opacity is already animating on the parent and
# stacking fractional opacities drops the whole subtree (the bug that forced
# the colophon-hold workaround in the original emitter).


def _check_grammar() -> None:
    """Fail loudly at import if the grammar is internally inconsistent.

    This exists because two entries once shared the id ``statement-right``.
    ``TREATMENTS`` is keyed by treatment id, so the later entry silently
    replaced the earlier one: the ``problem`` role quietly ended up with one
    treatment instead of two, and asking for that id on the role that "owned"
    it raised a role-mismatch error. Nothing failed at definition time; the
    grammar was simply smaller than it looked.

    That is the same failure mode as silently dropping an unknown key, so it
    gets the same remedy: refuse to be silent.
    """
    ids = [t.treatment_id for t in _TREATMENT_TABLE]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(
            f"duplicate treatment id(s) {duplicates}; treatment ids are global "
            f"because the grammar is keyed by id"
        )

    for role in ROLES:
        available = treatments_for_role(role)
        if len(available) != 2:
            raise ValueError(
                f"role {role!r} has {len(available)} treatment(s), expected exactly 2"
            )
        if not any(t.baseline for t in available):
            raise ValueError(f"role {role!r} has no baseline treatment")


_check_grammar()


def treatment_ids() -> tuple[str, ...]:
    return tuple(sorted(TREATMENTS))


def build_context(
    *, scene: Any, title: str | None, narration: str | None
) -> dict[str, Any]:
    """Assemble the precondition context for one scene."""
    combined = " ".join(p for p in (title, narration) if p)
    return {
        "scene": scene,
        "title": title or "",
        "narration": narration or "",
        "combined": combined,
        "numbers": numbers_in(combined),
    }


def validate_treatment(role: str, treatment: str, ctx: Mapping[str, Any]) -> None:
    """Raise if the treatment is not legal for the role/content.

    Raising (rather than silently substituting the baseline) is deliberate: if
    the planner asked for a treatment, the planner should hear that it did not
    get it.
    """
    entry = TREATMENTS.get(treatment)
    if entry is None:
        raise ValueError(f"unknown treatment {treatment!r}")
    if entry.role != role:
        raise ValueError(
            f"treatment {treatment!r} belongs to role {entry.role!r}, not {role!r}"
        )
    for pre in entry.preconditions:
        ok, why = pre(ctx)
        if not ok:
            raise ValueError(f"treatment {treatment!r} precondition failed: {why}")
