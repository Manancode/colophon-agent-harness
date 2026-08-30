"""The video review rubric, as code.

The *mechanism* here is adapted from the video review contract of an external
MIT-licensed agent skill (© 2026 Yaxin Luo). It is worth stealing wholesale
because every clause closes a way a review can be faked:

* Every dimension is scored on a 1-5 scale.
* A pass requires **every** dimension to reach the floor. An average cannot
  compensate for a weak dimension -- otherwise a model that loves its own
  work scores six dimensions 5 and quietly buries the one that is broken.
* The score vector must be complete and finite. Missing, boolean, NaN,
  infinite and out-of-range scores are rejected, not defaulted.
* The rubric itself is hashed and bound into the review, so a review recorded
  against one rubric cannot be replayed against a changed one.

The *dimensions* are colophon's, and deliberately not the source's. That
rubric scores research films and requires "a clean white primary canvas".
colophon's canvas is #0B0B0D and its output is product film, not conference
video -- copying the dimensions verbatim would have made colophon's own
default design a blocker in its own review. So the canvas rule is stated as
*"one flat declared surface tone"*: dark is as valid as light. What is
blocked is a transparent, tinted, gradient or image-filled root, which is
also exactly what breaks deterministic seeking. Two properties, one rule.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

FORMAT_VERSION = 1

#: The scale. Integer steps, so a reviewer cannot express false precision.
SCALE_MIN = 1
SCALE_MAX = 5

#: A pass needs EVERY dimension at or above this. There is no average.
MIN_PASSING_SCORE = 4

#: (name, question the reviewer answers). Seven, matching the source contract
#: -- six is the natural size, seven forces the motion question to be asked
#: explicitly instead of being absorbed into "composition".
DIMENSIONS: tuple[tuple[str, str], ...] = (
    (
        "hook",
        "Does the first scene earn the next ten seconds, before any "
        "explanation is given?",
    ),
    (
        "legibility",
        "Is every word readable at the size it is actually rendered, in "
        "motion, against the background it actually sits on?",
    ),
    (
        "evidence_grounding",
        "Is each number and claim visibly anchored to something the spec "
        "asserts, or does it read as decoration that merely looks credible?",
    ),
    (
        "composition_hierarchy",
        "Does each scene have one clear focal point and intentional "
        "density, or does it look filled rather than composed?",
    ),
    (
        "motion_continuity",
        "Does motion support comprehension -- coherent progression, nothing "
        "jittering, stuttering, or animating only to decorate?",
    ),
    (
        "pacing",
        "Does any scene drag, or get clipped before its point lands?",
    ),
    (
        "cta",
        "Is there exactly one unmistakable next action, and does the film "
        "end on it?",
    ),
)

#: Things that block regardless of how well everything else scores. Where a
#: deterministic gate already checks one of these, the gate's verdict wins
#: and the reviewer is not asked to re-litigate it.
HARD_BLOCKERS: tuple[str, ...] = (
    "invented_or_unbound_claim",
    "unreadable_or_clipped_text",
    "non_seekable_or_frame_clock_dependent_motion",
    "transparent_tinted_gradient_or_image_canvas",
    "remote_or_untrusted_asset",
    "inaudible_or_truncated_narration",
    "missing_or_forced_subtitles",
    "invalid_media_contract",
)

DIMENSION_NAMES: tuple[str, ...] = tuple(name for name, _ in DIMENSIONS)


class RubricError(ValueError):
    """A score vector does not satisfy the rubric."""


def rubric_document() -> dict[str, Any]:
    """The hashable rubric: structure, not prose.

    The dimension *questions* are deliberately excluded. Rewording a
    question should not invalidate every review ever recorded, but adding,
    removing or renaming a dimension changes what a score means and must.
    """
    return {
        "format_version": FORMAT_VERSION,
        "artifact_type": "colophon_video",
        "scale": {"min": SCALE_MIN, "max": SCALE_MAX},
        "minimum_passing_score_per_dimension": MIN_PASSING_SCORE,
        "dimensions": list(DIMENSION_NAMES),
        "hard_blockers": list(HARD_BLOCKERS),
    }


def rubric_sha256() -> str:
    """Fingerprint of the rubric itself. Changes only if the rubric does."""
    payload = json.dumps(
        rubric_document(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def rubric_markdown() -> str:
    """The reviewer's instructions, derived from the same source of truth.

    Generated rather than stored as a separate document, so the prose a
    reviewer reads and the structure a review is validated against cannot
    drift apart.
    """
    lines = [
        "# Video review rubric",
        "",
        f"Score every dimension from {SCALE_MIN} through {SCALE_MAX}:",
        "",
    ]
    for i, (name, question) in enumerate(DIMENSIONS, start=1):
        lines.append(f"{i}. `{name}` — {question}")
    lines += [
        "",
        f"For a `pass` verdict every dimension must independently score at "
        f"least {MIN_PASSING_SCORE}. A high average cannot compensate for a "
        f"weak dimension.",
        "Missing, boolean, NaN, infinite or out-of-range scores are invalid.",
        "",
        "A `blockers` entry is one of:",
        "",
    ]
    lines += [f"- `{b}`" for b in HARD_BLOCKERS]
    lines += [
        "",
        "**Canvas rule.** The composition may use any single flat surface "
        "tone, dark or light. A transparent, tinted, gradient or "
        "image-filled composition root is a blocker, both because it reads "
        "as unfinished and because it makes frames non-deterministic to "
        "seek to.",
        "",
        "A review you did not actually perform is worse than no review. Use "
        "`needs_visual_review` only when inspection was genuinely "
        "impossible, never to stand in for a partial one.",
    ]
    return "\n".join(lines) + "\n"


def validate_scores(scores: Any, *, verdict: str | None = None) -> dict[str, float]:
    """Reject anything that is not a complete, finite, in-range vector.

    Returns the scores coerced to float. Raises ``RubricError`` with every
    problem found rather than the first, so a reviewer fixing a rejected
    review sees the whole job at once.
    """
    problems: list[str] = []

    if not isinstance(scores, Mapping):
        raise RubricError(
            f"dimension scores must be an object, got {type(scores).__name__}"
        )

    expected = set(DIMENSION_NAMES)
    got = set(scores)
    if got != expected:
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("unexpected: " + ", ".join(extra))
        problems.append(
            "dimension scores must contain every rubric dimension exactly "
            "once (" + "; ".join(parts) + ")"
        )

    bad_value: list[str] = []
    for name in DIMENSION_NAMES:
        if name not in scores:
            continue
        value = scores[name]
        # bool is a subclass of int -- `True` would otherwise read as a
        # score of 1 and sail through.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            bad_value.append(f"{name}={value!r} (not a number)")
            continue
        as_float = float(value)
        if not math.isfinite(as_float):
            bad_value.append(f"{name}={value!r} (not finite)")
        elif not SCALE_MIN <= as_float <= SCALE_MAX:
            bad_value.append(f"{name}={value!r} (outside {SCALE_MIN}-{SCALE_MAX})")
    if bad_value:
        problems.append("invalid scores: " + ", ".join(bad_value))

    if verdict == "pass" and not problems:
        below = [
            name
            for name in DIMENSION_NAMES
            if float(scores[name]) < MIN_PASSING_SCORE
        ]
        if below:
            problems.append(
                f"pass requires every dimension >= {MIN_PASSING_SCORE}; "
                "below: " + ", ".join(below)
            )

    if problems:
        raise RubricError("; ".join(problems))

    return {name: float(scores[name]) for name in DIMENSION_NAMES}


def weakest_dimensions(scores: Mapping[str, Any]) -> list[str]:
    """Dimensions at or below the floor, worst first. Empty means all pass."""
    ranked = sorted(
        DIMENSION_NAMES, key=lambda n: (float(scores[n]), n)
    )
    return [n for n in ranked if float(scores[n]) < MIN_PASSING_SCORE] or []
