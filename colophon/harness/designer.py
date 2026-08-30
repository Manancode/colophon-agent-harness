"""The design-harness loop: from "it fails" to "it ships", one cheap fix at a time.

Plain English
=============

Up to now colophon *inspects* a video and reports problems. It never tried to
*fix* them. Phase 5 closes that gap with a loop:

    run the deterministic gates  ->  read the blockers  ->  fix the cheapest
    ones it can  ->  run the gates again  ->  repeat, but only so many times.

The crucial word is **cheapest**. Not every problem is equal. Some are dumb
arithmetic a computer can correct with certainty — "this scene lasts 0 seconds"
becomes "make it 4 seconds". Others are matters of taste a machine cannot judge
— "this frame is blank because the copy is weak". The loop routes each problem
to the fix that can actually solve it:

* **Mechanical** problems (a registered taxonomy code with a known, deterministic
  remedy) are patched in place, for free, every turn. No model, no network.
* **Everything else** (uncoded findings, anything that needs judgment) is handed
  to a *repair agent* — an LLM or external model. That seam is intentionally left
  unwired by default (see :class:`UnwiredRepairAgent`): colophon will mechanically
  fix what it can and otherwise stop, rather than guess at taste or call into
  something that is not there.

Two safety rails keep the loop honest:

* **A budget.** It tries at most ``MAX_DESIGNER_TURNS`` (30) turns, then stops.
* **A repeated-error abort.** If the *same set of blockers* comes back
  ``_MAX_REPEATED_VALIDATION_ERRORS`` (4) turns in a row — which means the fix
  (or the agent) is not actually moving the needle — it bails out in the
  ``blocked`` state and tells you exactly which findings remain. It never
  silently ships a broken video, and it never spins forever.

Where this came from
====================

The *shape* of this loop — a bounded designer loop that routes mechanical
blockers to a deterministic repair path before spending an expensive model call
on the rest, with a repeated-error abort — was learned from a studied design
harness (MIT, © 2026 Yaxin Luo). Colophon re-implements the mechanism against
its own closed-world taxonomy, and diverges on purpose in one important way:

* The reference routes by matching **text markers** on a composite blocker list
  (``text-overflow``, ``dom_audit``, …) with a "mostly mechanical" threshold.
* Colophon routes **per finding, by taxonomy code**, through a registry of
  deterministic remedies (``MECHANICAL_CODES``). That is strictly finer and
  consistent with colophon's fails-closed philosophy: a code is mechanical only
  if we have *proven* we can fix it, and anything unnamed still blocks.

Scope: the harness re-runs the **spec-level** gates (``spec_validate``,
``timeline_continuity``, ``narrative_order``, ``delivery_contract``). Render-
dependent gates (static HTML, scene structure, media contract, motion velocity)
require an actual encoded artifact and belong to the Phase 6 orchestration that
drives the renderer. A spec the harness reports ``ready`` is ready *at the spec
level*; the full render-and-reverify still happens in delivery.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Protocol, Sequence, Tuple

from ..qa.runner import run_stages
from ..qa.taxonomy import Assessment, Finding, assess
from ..repair.apply import RepairOp, apply_ops
from ..spec.schema import Scene, VideoSpec
from ..timeline.plan import build_plan


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

#: Maximum number of repair turns before the loop gives up. Mirrors the studied
#: harness's ``max_designer_turns``; 30 is enough that a genuine fix converges
#: and a stuck loop is obviously stuck well before any wall-clock problem.
MAX_DESIGNER_TURNS = 30

#: After this many *identical* blocker sets in a row, abort. The studied harness
#: used 4 for its validation-error signature; the same number fits here.
_MAX_REPEATED_VALIDATION_ERRORS = 4

#: The value the mechanical remedy assigns to a scene whose duration is missing
#: or non-positive. Above the delivery contract's 0.5s floor and a sane default
#: beat length; the author can always override afterwards.
DEFAULT_SCENE_DURATION_S = 4.0


# --------------------------------------------------------------------------
# Mechanical repair registry
# --------------------------------------------------------------------------
#
# The single source of truth for "which blockers can colophon fix for free".
# A code is mechanical only if a deterministic, non-destructive patch exists for
# it -- and the field it edits is on the repair whitelist (see
# ``colophon.repair.apply._SCENE_MUTABLE``). Today that is exactly
# ``spec.scene.duration``: a non-positive duration is corrected by clamping it to
# ``DEFAULT_SCENE_DURATION_S`` for every offending scene. Adding a code here is
# the extension point for future deterministic remedies; nothing else in the
# loop needs to change.

MechanicalRemedy = Callable[
    [VideoSpec, Finding], Tuple[list[RepairOp], dict[str, str]]
]


def _mech_fix_scene_duration(
    spec: VideoSpec, _finding: Finding
) -> Tuple[list[RepairOp], dict[str, str]]:
    """Clamp every non-positive scene duration to the default.

    Invariant-based, not message-parsing: the remedy enforces "every scene
    lasts longer than zero" across the whole spec rather than trying to read a
    scene id out of an error string. Fixing the root invariant also clears the
    timeline and delivery symptoms that the bad duration caused.
    """
    ops = [
        RepairOp(s.scene_id, "duration_s", DEFAULT_SCENE_DURATION_S)
        for s in spec.scenes
        if s.duration_s is None or s.duration_s <= 0
    ]
    return ops, {}


MECHANICAL_REMEDIES: dict[str, MechanicalRemedy] = {
    "spec.scene.duration": _mech_fix_scene_duration,
}

#: Codes the loop may patch deterministically. Membership here is what makes a
#: finding "mechanical"; everything else needs judgment (the LLM seam).
MECHANICAL_CODES = frozenset(MECHANICAL_REMEDIES)


# --------------------------------------------------------------------------
# The repair-agent seam (the expensive path)
# --------------------------------------------------------------------------
#
# Everything the mechanical registry cannot handle is offered to a repair agent.
# By default none is wired, so those findings simply persist and the loop either
# clears them transitively (if they were symptoms of a mechanical fault) or
# aborts once they repeat. Wire a real agent by passing an object with a
# ``repair(spec, findings) -> VideoSpec | None`` method.


class RepairAgent(Protocol):
    """Integration point for taste / judgment repairs.

    Implement this to wire an LLM or external agent. Return a corrected
    ``VideoSpec``, or ``None`` to decline (the loop then retries / aborts per
    its repeated-error policy).
    """

    def repair(
        self, *, spec: VideoSpec, findings: list[Finding]
    ) -> "VideoSpec | None":
        ...


@dataclass
class UnwiredRepairAgent:
    """The default seam: no external repair available, so it declines all.

    This is the documented integration point. It exists so the loop has a clear,
    honest default instead of crashing or silently inventing fixes. Replacing it
    with a real agent is the only change needed to enable the judgment path.
    """

    def repair(
        self, *, spec: VideoSpec, findings: list[Finding]
    ) -> "VideoSpec | None":
        return None


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


@dataclass
class DesignerSettings:
    """Tunables for the loop. Defaults match the constants above."""

    max_turns: int = MAX_DESIGNER_TURNS
    max_repeated_errors: int = _MAX_REPEATED_VALIDATION_ERRORS
    default_scene_duration_s: float = DEFAULT_SCENE_DURATION_S


# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------


@dataclass
class DesignTurn:
    """One iteration of the loop, recorded for review."""

    turn: int
    state_before: str
    mechanical_codes: tuple[str, ...]
    llm_codes: tuple[str, ...]
    applied_ops: tuple[RepairOp, ...]
    llm_outcome: str
    state_after: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "state_before": self.state_before,
            "mechanical_codes": list(self.mechanical_codes),
            "llm_codes": list(self.llm_codes),
            "applied_ops": [o.to_dict() for o in self.applied_ops],
            "llm_outcome": self.llm_outcome,
            "state_after": self.state_after,
            "note": self.note,
        }


@dataclass
class DesignSession:
    """The whole loop: what it tried, what it produced, whether it gave up."""

    turns_used: int
    final_spec: VideoSpec
    assessment: Assessment
    turns: list[DesignTurn] = field(default_factory=list)
    aborted: bool = False
    abort_reason: str | None = None

    @property
    def shippable(self) -> bool:
        return self.assessment.state != "blocked" and not self.aborted

    def to_dict(self) -> dict[str, Any]:
        return {
            "turns_used": self.turns_used,
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "final_state": self.assessment.state,
            "shippable": self.shippable,
            "final_spec_sha256": _hash_spec(self.final_spec),
            "turns": [t.to_dict() for t in self.turns],
            "assessment": self.assessment.to_dict(),
        }

    def __str__(self) -> str:
        head = (
            f"design loop: {self.turns_used} turn(s), "
            f"{'ABORTED' if self.aborted else 'completed'}"
        )
        lines = [head]
        if self.aborted and self.abort_reason:
            lines.append(f"  reason: {self.abort_reason}")
        lines.append(f"  final state: {self.assessment.state}")
        for t in self.turns:
            mech = ", ".join(t.mechanical_codes) or "-"
            llm = ", ".join(t.llm_codes) or "-"
            lines.append(
                f"  turn {t.turn}: mech=[{mech}] llm=[{llm}] "
                f"-> {t.state_after} | {t.llm_outcome}"
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _hash_spec(spec: VideoSpec) -> str:
    """Stable hash of the spec as authored, for logging only."""
    blob = json.dumps(spec.to_dict(), sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _blocker_signature(blockers: Sequence[Finding]) -> tuple[tuple[str, str], ...]:
    """A comparable key for "the same set of blockers came back".

    Two findings count as the same if both their code and message match. The
    message is included so two different scenes failing the same code are not
    collapsed into one key (that would hide a real change).
    """
    return tuple(sorted((f.code or "", f.message) for f in blockers))


def route_blockers(
    blockers: Sequence[Finding],
) -> tuple[list[Finding], list[Finding]]:
    """Split blockers into mechanical vs everything-else (needs judgment).

    Mechanical = its taxonomy code is in ``MECHANICAL_CODES`` and therefore has
    a registered deterministic remedy. Uncoded findings (unknown stage or code,
    which the taxonomy fails-closed into a blocker) can never be mechanical, so
    they are routed to the agent.
    """
    mechanical = [f for f in blockers if f.code in MECHANICAL_CODES]
    llm = [f for f in blockers if f.code not in MECHANICAL_CODES]
    return mechanical, llm


def _default_spec_stages() -> list[Callable[..., Any]]:
    """The spec-level gates the loop re-runs each turn.

    Imported lazily so this module loads even if a render-dependent stage has a
    heavy import it does not need. See the module docstring for why render-
    dependent stages are deliberately excluded.
    """
    from ..qa.stages.spec import (
        narrative_order,
        spec_validate,
        timeline_continuity,
    )
    from ..qa.stages.delivery import delivery_contract

    return [
        spec_validate,
        timeline_continuity,
        narrative_order,
        delivery_contract,
    ]


def _evaluate(
    spec: VideoSpec,
    stages: Sequence[Callable[..., Any]],
    contract: Any | None,
) -> Assessment:
    """Run the spec-level gates and classify the result."""
    plan = build_plan(spec)
    context: dict[str, Any] = {"spec": spec, "plan": plan}
    if contract is not None:
        context["contract"] = contract
    result = run_stages(stages, context, spec_sha256=_hash_spec(spec))
    return assess(result.results)


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------


def run_design_loop(
    spec: VideoSpec,
    *,
    llm: RepairAgent | None = None,
    contract: Any | None = None,
    settings: DesignerSettings | None = None,
    stages: Sequence[Callable[..., Any]] | None = None,
) -> DesignSession:
    """Repair ``spec`` until its spec-level gates pass, or stop trying.

    Parameters
    ----------
    spec:
        The spec to repair (treated as immutable; a new spec is returned).
    llm:
        Optional repair agent for findings that need judgment. ``None`` means
        mechanical-only mode.
    contract:
        Optional delivery contract; ``None`` uses the default.
    settings:
        Tunables (turn budget, repeat limit, default duration).
    stages:
        Override the spec-level gate set (mainly for tests).

    Returns
    -------
    DesignSession
        Every turn is logged; ``shippable`` is ``True`` iff the loop ended in a
        non-blocked state without aborting.
    """
    settings = settings or DesignerSettings()
    stages = stages or _default_spec_stages()
    llm = llm or UnwiredRepairAgent()

    last_sig: tuple[tuple[str, str], ...] | None = None
    repeat = 0
    turns: list[DesignTurn] = []
    aborted = False
    abort_reason: str | None = None
    current = spec

    def mk_turn(
        turn: int,
        before: str,
        mech_codes: tuple[str, ...],
        llm_codes: tuple[str, ...],
        ops: tuple[RepairOp, ...],
        llm_outcome: str,
        after: str,
        note: str,
    ) -> DesignTurn:
        return DesignTurn(
            turn=turn,
            state_before=before,
            mechanical_codes=mech_codes,
            llm_codes=llm_codes,
            applied_ops=ops,
            llm_outcome=llm_outcome,
            state_after=after,
            note=note,
        )

    for turn in range(settings.max_turns):
        state = _evaluate(current, stages, contract)

        # Stop as soon as no blocker remains. Warnings (e.g. advisory narrative
        # notes) are the reviewer's concern, not the loop's -- a spec with only
        # diagnostics is shippable and the loop is done.
        if not state.blockers:
            turns.append(
                mk_turn(
                    turn + 1,
                    state.state,
                    (),
                    (),
                    (),
                    "no blockers remain",
                    state.state,
                    "reached shippable",
                )
            )
            return DesignSession(
                turns_used=turn + 1,
                final_spec=current,
                assessment=state,
                turns=turns,
                aborted=False,
                abort_reason=None,
            )

        blockers = list(state.blockers)
        sig = _blocker_signature(blockers)
        if sig == last_sig:
            repeat += 1
        else:
            last_sig, repeat = sig, 1
        if repeat >= settings.max_repeated_errors:
            aborted = True
            abort_reason = (
                f"aborted after {repeat} identical turns: "
                + ", ".join(code or "<uncoded>" for code, _ in sig)
            )
            turns.append(
                mk_turn(
                    turn + 1,
                    state.state,
                    (),
                    (),
                    (),
                    "repeated identical blockers",
                    state.state,
                    abort_reason,
                )
            )
            return DesignSession(
                turns_used=turn + 1,
                final_spec=current,
                assessment=state,
                turns=turns,
                aborted=aborted,
                abort_reason=abort_reason,
            )

        mech, llm_findings = route_blockers(blockers)

        # 1) Apply every mechanical remedy (free, deterministic).
        patched = current
        applied_ops: list[RepairOp] = []
        if mech:
            ops: list[RepairOp] = []
            for finding in mech:
                new_ops, _claim_edits = MECHANICAL_REMEDIES[finding.code](
                    current, finding
                )
                ops.extend(new_ops)
            if ops:
                patched = apply_ops(current, ops).spec
                applied_ops = ops

        # 2) After mechanical repair, re-check. If it is already ready, stop.
        residual_llm = list(llm_findings)
        if patched is not current:
            after_mech = _evaluate(patched, stages, contract)
            if not after_mech.blockers:
                turns.append(
                    mk_turn(
                        turn + 1,
                        state.state,
                        tuple(f.code for f in mech),
                        (),
                        tuple(applied_ops),
                        "mechanical repair cleared all blockers",
                        after_mech.state,
                        "mechanical repair sufficed",
                    )
                )
                return DesignSession(
                    turns_used=turn + 1,
                    final_spec=patched,
                    assessment=after_mech,
                    turns=turns,
                    aborted=False,
                    abort_reason=None,
                )
            # Only the *remaining* (non-mechanical) blockers go to the agent.
            residual_llm = [
                f
                for f in after_mech.blockers
                if f.code not in MECHANICAL_CODES
            ]

        # 3) Offer the residual to the repair agent (if any, and if wired).
        llm_outcome = "no mechanical repair needed"
        if residual_llm and llm is not None:
            fixed = llm.repair(spec=patched, findings=list(residual_llm))
            if fixed is not None:
                patched = fixed
                llm_outcome = (
                    f"agent applied a revised spec for {len(residual_llm)} "
                    f"finding(s)"
                )
            else:
                llm_outcome = "agent declined to repair"
        elif residual_llm:
            llm_outcome = "no agent wired; uncoded blockers left to repeat/abort"

        current = patched
        after_state = _evaluate(current, stages, contract)
        turns.append(
            mk_turn(
                turn + 1,
                state.state,
                tuple(f.code for f in mech),
                tuple(f.code for f in residual_llm),
                tuple(applied_ops),
                llm_outcome,
                after_state.state,
                "turn complete",
            )
        )

    # Budget exhausted without reaching ready.
    aborted = True
    abort_reason = (
        f"exhausted budget of {settings.max_turns} turns without reaching ready"
    )
    final_state = _evaluate(current, stages, contract)
    turns.append(
        mk_turn(
            settings.max_turns,
            final_state.state,
            (),
            (),
            (),
            "budget exhausted",
            final_state.state,
            abort_reason,
        )
    )
    return DesignSession(
        turns_used=settings.max_turns,
        final_spec=current,
        assessment=final_state,
        turns=turns,
        aborted=aborted,
        abort_reason=abort_reason,
    )


#: Backwards-friendly alias.
design = run_design_loop
