"""Recording an independent visual review.

The review is a first-class artifact, not a comment in a chat log. It is
written to the attempt directory, bound to the spec hash, and folded into the
delivery report — so "this video was reviewed and passed" is a checkable
claim rather than a memory.

The rubric is deliberately short. Long rubrics get rubber-stamped.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: Dimensions a reviewer scores. Kept to six so the review stays honest.
RUBRIC: tuple[tuple[str, str], ...] = (
    ("hook", "Does the first scene earn the next ten seconds?"),
    ("legibility", "Is every word readable, at size, in motion?"),
    ("evidence", "Is each number and claim visibly anchored to something real?"),
    ("pacing", "Does any scene drag or feel clipped?"),
    ("variety", "Do the scenes look intentionally different, or like one template?"),
    ("cta", "Is there exactly one unmistakable next action?"),
)

VERDICTS = ("pass", "revise", "reject")


@dataclass
class ReviewRecord:
    reviewer: str
    verdict: str
    spec_sha256: str
    scene_hashes: dict[str, str] = field(default_factory=dict)
    scores: dict[str, int] = field(default_factory=dict)
    findings: list[dict[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=_now_stamp)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def blocking_findings(self) -> list[dict[str, str]]:
        return [f for f in self.findings if f.get("severity") == "blocking"]


def _now_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def blank_scores() -> dict[str, int]:
    return {name: 0 for name, _ in RUBRIC}


def rubric_markdown() -> str:
    lines = ["# Visual review rubric", ""]
    for i, (name, question) in enumerate(RUBRIC, start=1):
        lines.append(f"{i}. **{name}** — {question}")
    lines += [
        "",
        "Score each 1-5 (5 = no issues).",
        "",
        "Findings carry a `severity` of `blocking`, `major` or `minor`",
        "and, where possible, a `scene_id` so repair can be localized.",
        "",
        "Verdicts: `pass`, `revise`, `reject`.",
    ]
    return "\n".join(lines) + "\n"


def write_review(record: ReviewRecord, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def read_reviews(review_dir: str | Path) -> list[ReviewRecord]:
    review_dir = Path(review_dir)
    out: list[ReviewRecord] = []
    for path in sorted(review_dir.glob("review-*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        known = {f for f in ReviewRecord.__dataclass_fields__}
        out.append(ReviewRecord(**{k: v for k, v in raw.items() if k in known}))
    return out


def summarise(records: list[ReviewRecord]) -> dict[str, Any]:
    if not records:
        return {"reviewed": False, "verdict": None, "blocking": []}
    verdicts = [r.verdict for r in records]
    blocking = [f for r in records for f in r.blocking_findings]
    worst = "reject" if "reject" in verdicts else (
        "revise" if "revise" in verdicts else "pass"
    )
    return {
        "reviewed": True,
        "verdict": worst,
        "reviews": len(records),
        "blocking": blocking,
        "scores": {r.reviewer: r.scores for r in records},
    }
