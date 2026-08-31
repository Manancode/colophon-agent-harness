"""The gate catalog, and the two gate sets everything else should share.

Plain English
=============

Colophon has fourteen deterministic gates. They live across six modules, and
three separate call sites need to know the same two lists:

* *which gates can run before anything has been emitted?* (the spec-level set)
* *which gates run on a finished artifact?* (the full set)

Writing those lists down three times is how they drift apart, so this module
owns them once. It is the intended single source of truth; the CLI and the
design loop move onto it in a follow-up change.

It also answers a question an **agent** needs answered and a human does not:

    what does this gate need before it can tell the truth?

A gate that inspects a video says nothing useful before the video exists — it
reports "no video to check", and the taxonomy deliberately counts that as a
blocker (fail closed rather than pass on silence). A human reading that knows
to render first. An agent reading it does not, and will go hunting for a
defect in its own work that isn't there. So every gate is classified by the
cheapest artifact it needs:

* ``spec``     — runs on the spec and the timeline plan alone.
* ``project``  — needs the emitted HTML/CSS project.
* ``video``    — needs the encoded MP4.

The classification is **derived, not written down**: it reads each gate's own
parameter list (see :func:`needs_for`). When a gate grows a ``video_path``
parameter it becomes a video-tier gate with no edit here. A hand-maintained
table is a table that goes stale; this one cannot.

The one thing a signature cannot express is the difference between *accepting*
an artifact and *needing* it, so a gate in that position declares its own tier
with :func:`needs`. The declaration lives on the gate, not in a table here.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

# --------------------------------------------------------------------------
# Artifact tiers
# --------------------------------------------------------------------------

#: Context keys that exist before anything is emitted.
_SPEC_INPUTS = frozenset({"spec", "plan", "contract"})

#: Context keys that exist once the project has been emitted.
_PROJECT_INPUTS = frozenset({"document", "scene_fragments", "project_dir"})

#: Context keys that exist once the MP4 has been encoded.
_VIDEO_INPUTS = frozenset({"video_path"})

NEEDS_SPEC = "spec"
NEEDS_PROJECT = "project"
NEEDS_VIDEO = "video"

#: Ordered cheapest-to-dearest, so a caller can say "I only have a spec" and
#: filter on ``tier <= NEEDS_SPEC``.
TIERS = (NEEDS_SPEC, NEEDS_PROJECT, NEEDS_VIDEO)


@dataclass(frozen=True)
class GateInfo:
    """One gate, described well enough for an agent to reason about it."""

    stage_id: str
    #: ``spec`` | ``project`` | ``video`` — the cheapest artifact it needs.
    needs: str
    #: The gate's own one-line description, or its module's.
    summary: str
    #: The context keys the gate accepts, in signature order.
    inputs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage_id,
            "needs": self.needs,
            "summary": self.summary,
            "inputs": list(self.inputs),
        }


# --------------------------------------------------------------------------
# Derivation
# --------------------------------------------------------------------------


def _parameters(fn: Callable[..., Any]) -> tuple[str, ...]:
    return tuple(inspect.signature(fn).parameters)


def _first_line(text: str | None) -> str:
    """The first non-blank line of a docstring."""
    if not text:
        return ""
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


#: The attribute a gate sets to override its derived tier.
NEEDS_ATTRIBUTE = "colophon_needs"


def gate_needs(tier: str) -> Callable[[Any], Any]:
    """Declare the cheapest artifact a gate needs, when the signature overstates it.

    :func:`needs_for` reads a gate's parameters, which is right for every gate
    that *requires* what it names. It is wrong for a gate that merely accepts
    something, and the signature cannot tell the two apart:

    * ``media_contract`` returns "no video; run render first" and stops. It
      cannot say anything without the MP4, so it is genuinely video-tier.
    * ``scene_structure`` uses the video for one extra check and does real
      work without it. Calling it video-tier tells an agent it must render
      before this gate can speak — which is false, and which sends the agent
      off to render when it could have learned about a zero-duration scene or
      a missing asset straight from the plan.

    The declaration sits on the function, next to the parameter list it is
    correcting, rather than in a table here that would drift from both. Every
    gate that does not declare one is still derived from its signature.
    """
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; expected one of {TIERS}")

    def decorate(fn: Any) -> Any:
        setattr(fn, NEEDS_ATTRIBUTE, tier)
        return fn

    return decorate


def needs_for(fn: Callable[..., Any]) -> str:
    """The cheapest artifact ``fn`` needs before it can say anything true.

    Derived from the gate's parameter list: a gate that names ``video_path``
    needs a video, one that names ``document`` needs a project, anything else
    runs on the spec. A gate may correct that with :func:`needs` when it
    *accepts* an artifact without requiring it.

    Note that ``delivery_contract`` takes ``rendered_duration_s`` and stays in
    the spec tier on purpose: the tier keys on ``video_path`` alone, and that
    gate has no video parameter at all.
    """
    declared = getattr(fn, NEEDS_ATTRIBUTE, None)
    if declared is not None:
        return declared
    names = set(_parameters(fn))
    if names & _VIDEO_INPUTS:
        return NEEDS_VIDEO
    if names & _PROJECT_INPUTS:
        return NEEDS_PROJECT
    return NEEDS_SPEC


def summary_for(fn: Callable[..., Any]) -> str:
    """The gate's own one-line description.

    Stages that share a module (``static_html`` and ``canvas_audit``) have no
    docstring of their own and fall back to the module docstring, which
    describes both — still true, just less specific than it could be. Giving a
    stage its own docstring is the cheap fix, and needs no change here.
    """
    for text in (fn.__doc__, getattr(inspect.getmodule(fn), "__doc__", None)):
        line = _first_line(text)
        if line:
            return line
    return ""


def gate_info(fn: Callable[..., Any]) -> GateInfo:
    return GateInfo(
        stage_id=getattr(fn, "__name__", str(fn)),
        needs=needs_for(fn),
        summary=summary_for(fn),
        inputs=_parameters(fn),
    )


def gate_catalog(fns: Any) -> list[GateInfo]:
    """Describe every gate in ``fns``."""
    return [gate_info(fn) for fn in fns]


def gates_needing_no_more_than(
    fns: Any, tier: str = NEEDS_SPEC
) -> list[Callable[..., Any]]:
    """The subset of ``fns`` that can run given artifacts up to ``tier``.

    ``tier`` is inclusive: ``NEEDS_SPEC`` returns only the spec-level gates,
    ``NEEDS_VIDEO`` returns everything.
    """
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; expected one of {TIERS}")
    limit = TIERS.index(tier)
    return [fn for fn in fns if TIERS.index(needs_for(fn)) <= limit]


# --------------------------------------------------------------------------
# The two canonical gate sets
# --------------------------------------------------------------------------
#
# Imported lazily, matching the design loop: a spec-level caller should not pay
# for importing (and therefore constructing) the render-dependent stages it is
# never going to call.


def spec_gate_fns() -> list[Callable[..., Any]]:
    """The four gates that need nothing but the spec and the timeline plan."""
    from .stages.delivery import delivery_contract
    from .stages.spec import (
        narrative_order,
        spec_validate,
        timeline_continuity,
    )

    return [
        spec_validate,
        timeline_continuity,
        narrative_order,
        delivery_contract,
    ]


def full_gate_fns() -> list[Callable[..., Any]]:
    """Every gate, in the order ``colophon qa`` runs them."""
    from .stages.delivery import delivery_contract
    from .stages.grounding import claim_grounding
    from .stages.media import media_contract
    from .stages.motion_velocity import motion_pixel_velocity
    from .stages.spec import (
        narrative_order,
        spec_validate,
        timeline_continuity,
    )
    from .stages.static import canvas_audit, static_html
    from .stages.structure import scene_structure
    from .stages.taste import (
        ai_slop_detector,
        centerpiece_invariant,
        color_consistency,
        motion_accessibility,
    )

    return [
        spec_validate,
        timeline_continuity,
        narrative_order,
        static_html,
        canvas_audit,
        scene_structure,
        claim_grounding,
        ai_slop_detector,
        color_consistency,
        centerpiece_invariant,
        motion_accessibility,
        delivery_contract,
        motion_pixel_velocity,
        media_contract,
    ]
