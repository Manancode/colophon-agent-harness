"""The second critic, and how it meets the first.

colophon already runs a *rule* critic: the fourteen deterministic gates in
``colophon.qa``. Phase 4 adds the *visual* critic -- a fresh reviewer scoring
the artifact against the rubric in ``colophon.qa.rubric`` -- and merges the two
into the same three-state verdict the gates already produce
(``blocked`` / ``ready_with_warnings`` / ``ready``, from
``colophon.qa.taxonomy``).

The merge is deliberately asymmetric so the machine can never be talked out of
a hard fact:

1. **A gate blocker blocks.** The visual critic cannot overrule a gate: if the
   video fails the media contract, no score the reviewer gives matters.
2. **A rubric hard blocker blocks.** Those block on things no gate inspects
   for meaning -- an invented claim, a canvas that reads wrong.
3. **A pass is every dimension >= 4.** The rubric enforces this; an average
   cannot rescue one weak dimension.
4. **No review is not a pass.** With no independent review recorded, the run
   is ``ready_with_warnings`` at best, never ``ready``. The point of a second
   critic is that it actually ran.

The reviewer must be a *fresh* context that did not author the artifact. A
review an agent files about its own output is worthless -- the rule that
"a single reviewer will almost always approve its own work" is why this is a
separate critic at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..qa.rubric import (
    DIMENSION_NAMES,
    HARD_BLOCKERS,
    MIN_PASSING_SCORE,
    RubricError,
    validate_scores,
)
from ..qa.taxonomy import Assessment, Finding, Severity
from .context import ReviewContext

VERDICT_PASS = "pass"
VERDICT_REVISE = "revise"
VERDICT_REJECT = "reject"
VERDICT_NEEDS_VISUAL_REVIEW = "needs_visual_review"
ALLOWED_VERDICTS = (
    VERDICT_PASS,
    VERDICT_REVISE,
    VERDICT_REJECT,
    VERDICT_NEEDS_VISUAL_REVIEW,
)
#: The generator must never name itself as the reviewer.
GENERATOR_SENTINEL = "colophon-generator"


class ReviewError(ValueError):
    """A returned visual review does not satisfy the contract."""


@dataclass(frozen=True)
class ValidatedReview:
    reviewer: str
    reviewer_mode: str
    verdict: str
    scores: dict[str, float]
    blockers: tuple[str, ...]
    reviewed_frame_ids: tuple[str, ...]
    complete: bool


def validate_review(
    review: Any, context: ReviewContext
) -> ValidatedReview:
    """Reject anything that is not a faithful review of this context.

    The checks are the no-fakes guarantees: the bound hashes are copied back
    unchanged, the reviewed-frame set is the complete preview set, the score
    vector is complete and in range, and every declared blocker is a rubric
    id. Anything wrong is collected into one error so a reviewer fixing a
    rejected review sees the whole job at once.
    """
    if not isinstance(review, Mapping):
        raise ReviewError("review must be an object")
    problems: list[str] = []

    if not review.get("complete"):
        problems.append("review reports complete=False")

    verdict = review.get("verdict")
    if verdict not in ALLOWED_VERDICTS:
        problems.append(
            f"verdict must be one of {', '.join(ALLOWED_VERDICTS)}, got {verdict!r}"
        )

    reviewer = review.get("reviewer")
    if (
        not isinstance(reviewer, str)
        or not reviewer.strip()
        or reviewer.strip().lower() == GENERATOR_SENTINEL
    ):
        problems.append("reviewer must be named and must not be the generator")
    reviewer_mode = review.get("reviewer_mode")
    if not isinstance(reviewer_mode, str) or not reviewer_mode.strip():
        problems.append("reviewer_mode is required")

    if str(review.get("review_context_sha256", "")) != context.review_context_sha256:
        problems.append("review_context_sha256 does not match the bound context")
    if str(review.get("rubric_sha256", "")) != context.rubric_sha256:
        problems.append("rubric_sha256 does not match the bound context")
    for key, expected in context.artifact_hashes.items():
        got = (review.get("artifact_hashes") or {}).get(key)
        if str(got) != expected:
            problems.append(f"artifact_hashes[{key}] does not match the bound context")
    reviewed = review.get("reviewed_frame_ids")
    expected_ids = sorted(context.preview_hashes)
    if sorted(reviewed or []) != expected_ids:
        problems.append(
            "reviewed_frame_ids must be the complete preview set: "
            f"expected {expected_ids}, got {sorted(reviewed or [])}"
        )

    blockers = review.get("blockers", [])
    if not isinstance(blockers, list) or any(
        not isinstance(b, str) or b not in HARD_BLOCKERS for b in blockers
    ):
        problems.append("blockers must be ids from the rubric's hard-blocker set")

    if verdict == VERDICT_NEEDS_VISUAL_REVIEW:
        scores_f: dict[str, float] = {}
    else:
        try:
            scores_f = validate_scores(
                review.get("dimension_scores", {}),
                verdict=verdict if verdict != VERDICT_NEEDS_VISUAL_REVIEW else None,
            )
        except RubricError as exc:
            problems.append(str(exc))

    if problems:
        raise ReviewError("invalid visual review: " + "; ".join(problems))

    return ValidatedReview(
        reviewer=str(reviewer).strip(),
        reviewer_mode=str(reviewer_mode).strip(),
        verdict=str(verdict),
        scores=scores_f,
        blockers=tuple(str(b) for b in blockers),
        reviewed_frame_ids=tuple(sorted(reviewed or [])),
        complete=bool(review.get("complete")),
    )


def _finding(
    message: str, code: str, severity: Severity
) -> Finding:
    """Build a visual-critic finding without registering it in the taxonomy.

    These findings are produced by code, not by a registry lookup, so they
    are marked ``known=True`` explicitly and circumvent the fails-closed
    default that would otherwise treat an unknown code as a blocker.
    """
    return Finding(
        stage_id="visual_review",
        message=message,
        code=code,
        severity=severity,
        known=True,
    )


def merge_verdict(
    *,
    deterministic: Assessment,
    review: ValidatedReview | None,
) -> Assessment:
    """Combine the rule critic and the visual critic into one verdict."""
    blockers = list(deterministic.blockers)
    warnings = list(deterministic.warnings)

    if review is None:
        # The deterministic gates passed but the semantic layer never ran.
        warnings.append(
            _finding(
                "no independent visual review recorded; the deterministic "
                "gates passed but the semantic layer did not run",
                "visual_review.missing",
                Severity.DIAGNOSTIC,
            )
        )
        return Assessment("ready_with_warnings", tuple(blockers), tuple(warnings))

    if review.blockers:
        for b in review.blockers:
            blockers.append(
                _finding(f"visual blocker: {b}", f"visual_review.{b}", Severity.BLOCKER)
            )
    if review.verdict == VERDICT_REJECT:
        blockers.append(
            _finding(
                "the visual reviewer rejected the artifact",
                "visual_review.reject",
                Severity.BLOCKER,
            )
        )
    elif review.verdict == VERDICT_NEEDS_VISUAL_REVIEW:
        warnings.append(
            _finding(
                "the reviewer could not perform a visual review",
                "visual_review.needs_visual_review",
                Severity.DIAGNOSTIC,
            )
        )
    elif review.verdict == VERDICT_REVISE:
        warnings.append(
            _finding(
                "the visual reviewer asked for revisions",
                "visual_review.revise",
                Severity.DIAGNOSTIC,
            )
        )
    elif review.verdict == VERDICT_PASS:
        # validate_review already guaranteed every dimension >= the floor,
        # so a passing review adds no weak-dimension warnings here.
        pass

    # The deterministic verdict is authoritative about hard stops: a gate
    # that already blocked the run cannot be overruled by a glowing review.
    if blockers or deterministic.state == "blocked":
        state = "blocked"
    elif warnings or deterministic.state == "ready_with_warnings":
        state = "ready_with_warnings"
    else:
        state = "ready"
    return Assessment(state, tuple(blockers), tuple(warnings))
