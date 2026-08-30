"""The closed world of things that can go wrong.

Every QA stage reports *problems*. This module answers one question about
them: does this problem stop the delivery, or is it something a reviewer
should see but we can still ship?

The answer is not computed from the problem text. It is looked up in a
registry, and **anything not in the registry is treated as a blocker.**

That last clause is the whole point, so it is worth being precise about why.

A checker that classifies problems by pattern-matching their text has a
failure mode that is invisible: when a new kind of problem appears that
nobody wrote a rule for, the matcher simply finds nothing, concludes the
problem is unknown-but-presumably-minor, and lets it through. The system
gets *more* permissive exactly when it is most confused. Every escape from
a quality gate in practice looks like this, not like a rule that fired
incorrectly.

Inverting the default fixes it. An unrecognised problem is not evidence
that a thing is safe; it is evidence that we do not know what it is. So it
blocks. The registry can only ever make the system *stricter than its
author was careless* — never looser. Adding a code is a deliberate act that
says "I have looked at this and it is cosmetic"; forgetting to add one
costs you a blocked run, which is a bug you notice immediately, rather than
a silently shipped defect, which is one you notice in production.

Consequence worth stating plainly: this module is intentionally incomplete,
and that is safe. Coverage grows as gates are taught to emit codes, and
until then un-named problems fail loudly instead of passing quietly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

#: Bump when the meaning of any code changes, not when codes are added.
#: A pass recorded under v1 must not be re-read under v2 and still count.
TAXONOMY_VERSION = "colophon-video-v1"


class Severity(str, Enum):
    """What a finding does to a delivery."""

    #: Stops it. Either it is broken or we do not know what it is.
    BLOCKER = "blocker"
    #: Ships, but a reviewer sees it.
    DIAGNOSTIC = "diagnostic"


@dataclass(frozen=True)
class StagePolicy:
    """A registered QA stage and the severity its problems default to.

    ``default_severity`` applies only when a stage reports a problem without
    a code. A stage that emits codes gets to be precise per problem; one that
    does not falls back to a single honest answer for the whole stage.
    """

    stage_id: str
    description: str
    default_severity: Severity = Severity.BLOCKER


@dataclass(frozen=True)
class FailureMode:
    """One specific, named way a run can be wrong.

    ``remedy`` is not decoration. A taxonomy that only says "this is broken"
    makes the operator go read the gate that produced it; one that says what
    to do about it is the difference between a gate and a workflow.
    """

    code: str
    stage_id: str
    severity: Severity
    summary: str
    remedy: str


# --------------------------------------------------------------------------
# Registered stages
# --------------------------------------------------------------------------
# Keep in sync with the stage lists in cli.py. `check_registry()` below does
# not enforce that (it cannot see the CLI), but `assess()` blocks any
# unregistered stage that reports a problem, so a stage added to the CLI and
# forgotten here fails its first run rather than passing silently.

STAGES: dict[str, StagePolicy] = {
    s.stage_id: s
    for s in (
        StagePolicy("spec_validate", "The spec is internally consistent."),
        StagePolicy("timeline_continuity", "Scenes tile the clock with no gaps."),
        StagePolicy(
            "narrative_order",
            "The running order is structurally conventional.",
            Severity.DIAGNOSTIC,
        ),
        StagePolicy("static_html", "The emitted document is inert and self-contained."),
        StagePolicy("canvas_audit", "The stage matches the declared canvas."),
        StagePolicy("claim_grounding", "Every claim on screen is a bound claim."),
        StagePolicy("ai_slop_detector", "No generated-design tells in the CSS."),
        StagePolicy("color_consistency", "The emitted accent equals the brand accent."),
        StagePolicy("centerpiece_invariant", "One focal element per scene."),
        StagePolicy("motion_accessibility", "Motion can be opted out of; no flicker."),
        StagePolicy("delivery_contract", "The spec is a shippable video."),
        StagePolicy("motion_pixel_velocity", "Motion moves at least a pixel per frame."),
        StagePolicy("media_contract", "The encoded file matches the plan."),
    )
}


# --------------------------------------------------------------------------
# Named failure modes
# --------------------------------------------------------------------------
# Seeded from the checks that exist today. Not exhaustive by design; see the
# module docstring for why that is safe rather than merely unfinished.


def _mode(code: str, stage_id: str, severity: Severity, summary: str, remedy: str):
    return FailureMode(code, stage_id, severity, summary, remedy)


FAILURE_MODES: dict[str, FailureMode] = {
    m.code: m
    for m in (
        # ---- spec_validate -------------------------------------------
        _mode("spec.id.empty", "spec_validate", Severity.BLOCKER,
              "spec_id is empty",
              "Give the spec a stable spec_id; it is what runs are keyed by."),
        _mode("spec.scenes.empty", "spec_validate", Severity.BLOCKER,
              "spec has no scenes",
              "Add at least one scene."),
        _mode("spec.canvas.dimensions", "spec_validate", Severity.BLOCKER,
              "canvas dimensions are not positive",
              "Set canvas.width and canvas.height to the delivery size."),
        _mode("spec.canvas.fps", "spec_validate", Severity.BLOCKER,
              "canvas.fps is not an allowed frame rate",
              "Use one of the allowed fps values."),
        _mode("spec.brand.missing", "spec_validate", Severity.BLOCKER,
              "the spec has no brand block",
              "Add brand with a name and the required tokens."),
        _mode("spec.brand.name", "spec_validate", Severity.BLOCKER,
              "brand.name is empty",
              "Name the product; the hook scene renders it."),
        _mode("spec.brand.token", "spec_validate", Severity.BLOCKER,
              "a required brand token is missing",
              "Add the missing token to brand.tokens."),
        _mode("spec.timeline.policy", "spec_validate", Severity.BLOCKER,
              "timeline.policy is not allowed",
              "Use a supported timeline policy."),
        _mode("spec.timeline.transition", "spec_validate", Severity.BLOCKER,
              "timeline.transition is not allowed",
              "Use a supported transition."),
        _mode("spec.timeline.transition_ms", "spec_validate", Severity.BLOCKER,
              "timeline.transition_ms is negative",
              "A transition length cannot be negative."),
        _mode("spec.timeline.overlap_s", "spec_validate", Severity.BLOCKER,
              "timeline.overlap_s is negative",
              "Overlap is a duration shared between neighbours; it cannot be negative."),
        _mode("spec.timeline.match_cut_needs_overlap", "spec_validate",
              Severity.BLOCKER,
              "a match-cut transition was requested with no overlap",
              "A match cut joins two scenes through the frames they share, so it "
              "needs overlap_s > 0. Raise the overlap or pick another transition."),
        _mode("spec.asset.kind", "spec_validate", Severity.BLOCKER,
              "an asset declares an unknown kind",
              "Use a supported asset kind."),
        _mode("spec.asset.remote", "spec_validate", Severity.BLOCKER,
              "an asset points at a remote URL",
              "Vendor the asset locally; a build must not depend on the network."),
        _mode("spec.asset.path", "spec_validate", Severity.BLOCKER,
              "an asset has an empty path",
              "Give the asset a path, or remove it."),
        _mode("spec.asset.id_duplicate", "spec_validate", Severity.BLOCKER,
              "two assets share an id",
              "Asset ids are unique; duplicates make references ambiguous."),
        _mode("spec.claim.kind", "spec_validate", Severity.BLOCKER,
              "a claim declares an unknown kind",
              "Use a supported claim kind."),
        _mode("spec.claim.text", "spec_validate", Severity.BLOCKER,
              "a claim has empty text",
              "Write the claim, or remove it."),
        _mode("spec.claim.id_duplicate", "spec_validate", Severity.BLOCKER,
              "two claims share an id",
              "Claim ids are unique; duplicates make grounding ambiguous."),
        _mode("spec.claim.unreferenced", "spec_validate", Severity.BLOCKER,
              "a claim is not referenced by any scene",
              "Bind the claim to a scene title or narration, or delete it."),
        _mode("spec.scene.role", "spec_validate", Severity.BLOCKER,
              "a scene uses a role outside the closed set",
              "Use one of the six canonical roles."),
        _mode("spec.scene.treatment", "spec_validate", Severity.BLOCKER,
              "a scene has an empty treatment",
              "Pick a treatment for the scene's role."),
        _mode("spec.scene.id_duplicate", "spec_validate", Severity.BLOCKER,
              "two scenes share an id",
              "Scene ids are unique; duplicates make repair ambiguous."),
        _mode("spec.scene.duration", "spec_validate", Severity.BLOCKER,
              "a scene has a non-positive duration",
              "Give the scene a positive duration in seconds."),
        _mode("spec.scene.motion", "spec_validate", Severity.BLOCKER,
              "a scene names a motion outside the closed set",
              "Use one of the declared motions."),
        _mode("spec.scene.motion_unsupported", "spec_validate", Severity.BLOCKER,
              "a scene pairs a treatment with a motion it cannot carry",
              "Pick a motion the treatment supports. A motion whose target "
              "element is never emitted renders as a silent no-op."),
        _mode("spec.scene.title_claim_kind", "spec_validate", Severity.BLOCKER,
              "a scene's title claim is not a title-kind claim",
              "Point title_claim_id at a claim whose kind is 'title'."),
        _mode("spec.scene.claim_ref", "spec_validate", Severity.BLOCKER,
              "a scene references a claim that does not exist",
              "Point the scene at a claim id that is in the spec."),
        _mode("spec.scene.asset_ref", "spec_validate", Severity.BLOCKER,
              "a scene references an asset that does not exist",
              "Point the scene at an asset id that is in the spec."),
        # ---- timeline_continuity -------------------------------------
        _mode("timeline.start", "timeline_continuity", Severity.BLOCKER,
              "the first scene does not start at frame 0",
              "Rebuild the plan; scene starts are derived, never authored."),
        _mode("timeline.gap", "timeline_continuity", Severity.BLOCKER,
              "there is an unplayed gap between two scenes",
              "A gap renders as dead air. Check the overlap policy."),
        _mode("timeline.overlap", "timeline_continuity", Severity.BLOCKER,
              "two scenes overlap by more than the declared maximum",
              "Raise timeline.overlap_s or shorten the scenes."),
        _mode("timeline.duration", "timeline_continuity", Severity.BLOCKER,
              "a scene has a non-positive duration in frames",
              "Lengthen the scene past one frame."),
        _mode("timeline.overflow", "timeline_continuity", Severity.BLOCKER,
              "a scene ends past the end of the composition",
              "Rebuild the plan; this indicates the total was computed wrongly."),
        # ---- narrative_order (advisory) ------------------------------
        _mode("narrative.first_cta", "narrative_order", Severity.DIAGNOSTIC,
              "the video opens on the call to action",
              "Lead with the hook; the CTA belongs last."),
        _mode("narrative.last_not_cta", "narrative_order", Severity.DIAGNOSTIC,
              "the video does not end on the call to action",
              "End on the CTA, or drop it and say why."),
        _mode("narrative.no_hook", "narrative_order", Severity.DIAGNOSTIC,
              "no scene has the hook role",
              "Add a hook; it is what earns the next ten seconds."),
        _mode("narrative.proof_before_capability", "narrative_order",
              Severity.DIAGNOSTIC,
              "evidence appears before the mechanism it evidences",
              "Show what the product does before showing what it achieved."),
        # ---- static_html ---------------------------------------------
        _mode("html.duplicate_attr", "static_html", Severity.BLOCKER,
              "an element repeats an attribute",
              "Emit each attribute once; duplicate attributes are dropped silently "
              "by HTML parsers and the value you get is not the one you wrote."),
        _mode("html.inline_handler", "static_html", Severity.BLOCKER,
              "the document contains an inline event handler",
              "Remove it. Motion must be declarative so the encoder can seek to "
              "any frame."),
        _mode("html.remote_ref", "static_html", Severity.BLOCKER,
              "the document references a remote resource",
              "Inline or vendor it; a render must not depend on the network."),
        _mode("html.unsafe_embed", "static_html", Severity.BLOCKER,
              "the document embeds content that can execute",
              "Remove the embed."),
        _mode("html.no_composition_root", "static_html", Severity.BLOCKER,
              "no composition root was found in the document",
              "The emitter must stamp a composition root; without it the renderer "
              "cannot find scene boundaries."),
        # ---- delivery_contract ---------------------------------------
        _mode("delivery.canvas", "delivery_contract", Severity.BLOCKER,
              "the canvas is not the contracted delivery size",
              "Render at the contracted size; rescaling after encode loses quality."),
        _mode("delivery.fps", "delivery_contract", Severity.BLOCKER,
              "the frame rate is not the contracted rate",
              "Use the contracted fps."),
        _mode("delivery.duration_envelope", "delivery_contract", Severity.BLOCKER,
              "the video's length is outside the deliverable envelope",
              "Add or cut scenes, or pass a contract that admits the format."),
        _mode("delivery.scene_count", "delivery_contract", Severity.BLOCKER,
              "the scene count is outside the deliverable range",
              "Split or merge scenes."),
        _mode("delivery.scene_too_short", "delivery_contract", Severity.BLOCKER,
              "a scene is too short to register as a beat",
              "Lengthen it past the minimum."),
        _mode("delivery.duplicate_scene_id", "delivery_contract", Severity.BLOCKER,
              "two scenes share an id",
              "Scene ids are unique; duplicates make repair ambiguous."),
        _mode("delivery.render_drift", "delivery_contract", Severity.BLOCKER,
              "the encoded length drifts from the timeline",
              "The encoder dropped or padded frames. Re-render; if it persists, "
              "the timeline and the encoder disagree about frame count."),
    )
}

#: Codes the taxonomy recognises. Membership here is what makes a finding
#: known; everything else blocks.
KNOWN_CODES = frozenset(FAILURE_MODES)


# --------------------------------------------------------------------------
# Assessment
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One problem, classified."""

    stage_id: str
    message: str
    code: str | None
    severity: Severity
    #: False when the stage or code is not in the registry. Unknown findings
    #: are always blockers, so this is only ever False alongside BLOCKER.
    known: bool


@dataclass(frozen=True)
class Assessment:
    """Whether a run ships, and what stands in the way."""

    state: str  # "blocked" | "ready_with_warnings" | "ready"
    blockers: tuple[Finding, ...] = ()
    warnings: tuple[Finding, ...] = ()
    taxonomy_version: str = TAXONOMY_VERSION

    @property
    def shippable(self) -> bool:
        return self.state != "blocked"

    @property
    def unknowns(self) -> tuple[Finding, ...]:
        return tuple(f for f in (*self.blockers, *self.warnings) if not f.known)

    def to_dict(self) -> dict[str, object]:
        def dump(findings: tuple[Finding, ...]) -> list[dict[str, object]]:
            return [
                {
                    "stage_id": f.stage_id,
                    "code": f.code,
                    "severity": f.severity.value,
                    "known": f.known,
                    "message": f.message,
                }
                for f in findings
            ]

        return {
            "state": self.state,
            "shippable": self.shippable,
            "taxonomy_version": self.taxonomy_version,
            "blockers": dump(self.blockers),
            "warnings": dump(self.warnings),
        }

    def __str__(self) -> str:
        head = {
            "blocked": "BLOCKED",
            "ready_with_warnings": "READY (with warnings)",
            "ready": "READY",
        }[self.state]
        lines = [f"{head}  [{self.taxonomy_version}]"]
        for f in self.blockers:
            tag = "?" if not f.known else "x"
            body = _strip_stage_prefix(f.message, f.stage_id)
            lines.append(f"  [{tag}] {f.code or f.stage_id}: {body}")
        for f in self.warnings:
            body = _strip_stage_prefix(f.message, f.stage_id)
            lines.append(f"  [!] {f.code or f.stage_id}: {body}")
        unk = len(self.unknowns)
        if unk:
            lines.append(
                f"  {unk} finding(s) are not in the taxonomy and block by default"
            )
        return "\n".join(lines)


def _strip_stage_prefix(message: str, stage_id: str) -> str:
    """Drop a leading ``stage_id: `` from a problem message.

    Several gates prefix their own name onto every message, which was useful
    when problems were printed as a flat list and is pure noise now that the
    stage is shown separately. Display-only: the stored message is untouched
    so anything matching on it keeps working.
    """
    prefix = f"{stage_id}: "
    return message[len(prefix):] if message.startswith(prefix) else message


def classify(
    stage_id: str,
    message: str,
    code: str | None = None,
) -> Finding:
    """Decide what one problem does to the delivery.

    Unknown stage or unknown code -> blocker. That is the fails-closed rule,
    and it is the only default in this module that errs toward stopping.
    """
    stage = STAGES.get(stage_id)
    mode = FAILURE_MODES.get(code) if code else None

    if stage is None:
        return Finding(stage_id, message, code, Severity.BLOCKER, known=False)
    if code is not None and mode is None:
        return Finding(stage_id, message, code, Severity.BLOCKER, known=False)
    if mode is not None:
        return Finding(stage_id, message, code, mode.severity, known=True)
    return Finding(stage_id, message, None, stage.default_severity, known=True)


def assess(results: Sequence[object]) -> Assessment:
    """Classify every problem a pipeline run produced.

    Accepts ``StageResult`` objects (duck-typed, so this module does not
    import the runner and create a cycle). A result carrying ``codes`` gets
    per-problem precision; one without falls back to its stage default.

    Note that a stage marked advisory is *not* automatically a warning: the
    advisory flag lives on the stage, while severity lives on the problem.
    When a stage emits codes, the codes win, because per-problem knowledge is
    strictly better than a whole-stage guess.
    """
    blockers: list[Finding] = []
    warnings: list[Finding] = []

    for result in results:
        problems = list(getattr(result, "problems", ()) or ())
        if not problems:
            continue
        codes = list(getattr(result, "codes", ()) or ())
        stage_id = getattr(result, "stage_id", "<unknown>")

        for i, problem in enumerate(problems):
            code = codes[i] if i < len(codes) else None
            finding = classify(stage_id, str(problem), code)
            (blockers if finding.severity is Severity.BLOCKER else warnings).append(
                finding
            )

    if blockers:
        state = "blocked"
    elif warnings:
        state = "ready_with_warnings"
    else:
        state = "ready"

    return Assessment(state, tuple(blockers), tuple(warnings))


# --------------------------------------------------------------------------
# Registry self-check
# --------------------------------------------------------------------------


def _check_registry() -> None:
    """Refuse to import if the registry contradicts itself.

    Two entries sharing a code would mean the later silently replaced the
    earlier -- the same class of bug that already cost this project a
    treatment, so it gets the same remedy: say so at import time.

    Also enforces that every code names a stage that exists, so a typo in a
    stage_id cannot quietly orphan a rule.
    """
    orphans = sorted({m.stage_id for m in FAILURE_MODES.values()} - set(STAGES))
    if orphans:
        raise ValueError(
            f"failure modes reference unregistered stage(s) {orphans}; "
            f"registered: {sorted(STAGES)}"
        )
    if len(FAILURE_MODES) != len(list(FAILURE_MODES.values())):
        raise ValueError("duplicate failure-mode code(s)")


_check_registry()


@dataclass
class RegistryStats:
    """For the CLI and for tests: how much of the world is named."""

    stages: int
    codes: int
    stages_with_codes: int = 0
    diagnostic_codes: int = 0


def stats() -> RegistryStats:
    coded = {m.stage_id for m in FAILURE_MODES.values()}
    return RegistryStats(
        stages=len(STAGES),
        codes=len(FAILURE_MODES),
        stages_with_codes=len(coded),
        diagnostic_codes=sum(
            1 for m in FAILURE_MODES.values() if m.severity is Severity.DIAGNOSTIC
        ),
    )
