"""The deterministic QA pipeline.

Stages are pure functions of (spec, plan, artifacts) that return a
``StageResult``. They do not mutate inputs, do not talk to each other, and do
not depend on ordering — so any single stage can be re-run in isolation during
repair, which is the property localized repair depends on.

A stage either passes or produces problems. Advisory stages record problems
without failing the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence


@dataclass
class StageResult:
    stage_id: str
    passed: bool
    problems: list[str] = field(default_factory=list)
    advisory: bool = False
    detail: dict[str, Any] = field(default_factory=dict)
    #: Taxonomy code per problem, positionally parallel to ``problems``. Empty
    #: means the stage has not been taught to name its failures yet, and the
    #: taxonomy falls back to this stage's default severity. Shorter than
    #: ``problems`` is tolerated; the tail is simply unclassified.
    #:
    #: Why optional rather than required: making it mandatory would mean no
    #: stage reports a code until all of them do, and the taxonomy's whole
    #: value is that un-named problems block instead of passing. Partial
    #: adoption is therefore safe by construction, and this field can be
    #: filled in one gate at a time.
    codes: list[str | None] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return not self.passed and not self.advisory

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage_id,
            "passed": self.passed,
            "advisory": self.advisory,
            "problems": list(self.problems),
            "detail": self.detail,
            "codes": list(self.codes),
        }

    def __str__(self) -> str:
        if self.passed and not self.problems:
            return f"PASS  {self.stage_id}"
        tag = "PASS" if self.passed else "FAIL"
        if self.advisory:
            tag = "NOTE"
        head = f"{tag}  {self.stage_id}"
        lines = [head] + [f"        - {p}" for p in self.problems[:10]]
        if len(self.problems) > 10:
            lines.append(f"        … and {len(self.problems) - 10} more")
        return "\n".join(lines)


Stage = Callable[..., StageResult]


@dataclass
class PipelineResult:
    results: list[StageResult]
    spec_sha256: str = ""

    @property
    def passed(self) -> bool:
        return all(not r.blocking for r in self.results)

    @property
    def problems(self) -> list[str]:
        out: list[str] = []
        for r in self.results:
            out.extend(f"[{r.stage_id}] {p}" for p in r.problems)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "spec_sha256": self.spec_sha256,
            "stages": [r.to_dict() for r in self.results],
        }

    def stage(self, stage_id: str) -> StageResult | None:
        return next((r for r in self.results if r.stage_id == stage_id), None)


def run_stages(
    stages: Sequence[Stage], context: dict[str, Any], *, spec_sha256: str = ""
) -> PipelineResult:
    """Run stages in order, collecting every result.

    A raising stage becomes a failed stage rather than aborting the run —
    seeing all failures at once is worth more than a clean traceback.
    """
    results: list[StageResult] = []
    for stage in stages:
        try:
            results.append(stage(**context))
        except Exception as exc:  # noqa: BLE001 - deliberately broad
            name = getattr(stage, "__name__", str(stage))
            results.append(
                StageResult(
                    stage_id=name,
                    passed=False,
                    problems=[f"stage raised {type(exc).__name__}: {exc}"],
                )
            )
    return PipelineResult(results=results, spec_sha256=spec_sha256)


def format_report(result: PipelineResult) -> str:
    lines = [str(r) for r in result.results]
    verdict = "PASS" if result.passed else "FAIL"
    lines.append("")
    lines.append(f"{'=' * 60}")
    lines.append(f"{verdict}  ({sum(1 for r in result.results if r.passed)}"
                 f"/{len(result.results)} stages passed)")
    return "\n".join(lines)
