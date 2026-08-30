"""Harness matrix: compare colophon's deterministic judge against other harnesses.

The shape is the same one the other repos use: run the SAME briefs through
several harnesses, collect a matrix of pass/fail plus which gates fired, and
let the matrix argue about which harness is actually better.

colophon's own 14 deterministic gates are one harness (``colophon``). A naive
"raw agent" baseline (``naive``) is the contrast: it only checks that *something*
was produced, the way an unchecked LLM agent would. Plug real codex / claude /
deepseek harnesses in by implementing the same ``Harness`` callable (see
``ExternalAgentHarness``).

The matrix is runnable today without a browser: ``colophon_harness`` runs the 7
artifact-level gates on an already-emitted document, so the demonstration proves
the judge is a real measuring instrument, not a coin flip.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable

from ..qa.runner import run_stages
from ..qa.stages import motion_velocity as motion_velocity_stage
from ..qa.stages import static as static_stage
from ..qa.stages import taste as taste_stage
from ..runtime.tools import effective_path
from ..spec.schema import VideoSpec

#: The artifact-level gates — they measure an emitted document without needing
#: a rendered MP4 (that is what media_contract requires, added in production).
ARTIFACT_STAGES = [
    static_stage.static_html,
    static_stage.canvas_audit,
    taste_stage.ai_slop_detector,
    taste_stage.color_consistency,
    taste_stage.centerpiece_invariant,
    taste_stage.motion_accessibility,
    motion_velocity_stage.motion_pixel_velocity,
]


@dataclass
class HarnessResult:
    harness: str
    brief: str
    passed: bool
    gates: dict[str, bool] = field(default_factory=dict)
    skipped: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "harness": self.harness,
            "brief": self.brief,
            "passed": self.passed,
            "skipped": self.skipped,
            "gates": dict(self.gates),
            "detail": self.detail,
        }


#: A harness is a callable: (document, *, spec=None, brief="") -> HarnessResult,
#: and carries a ``.name`` attribute.
Harness = Callable[..., HarnessResult]


def _demo_spec() -> VideoSpec:
    """A minimal valid spec for artifact-level gate checks (brand=None, no
    scenes, default canvas background + 30fps)."""
    return VideoSpec(spec_id="bench", title="benchmark")


def colophon_harness(
    document: str, *, spec: VideoSpec | None = None, brief: str = "", **_: Any
) -> HarnessResult:
    """Run colophon's artifact gates on an emitted document."""
    spec = spec or _demo_spec()
    result = run_stages(
        ARTIFACT_STAGES,
        {"spec": spec, "document": document, "scene_fragments": None},
        spec_sha256="",
    )
    gates = {r.stage_id: (not r.blocking) for r in result.results}
    return HarnessResult(
        harness="colophon",
        brief=brief,
        passed=result.passed,
        gates=gates,
    )


colophon_harness.name = "colophon"


def naive_harness(
    document: str, *, spec: VideoSpec | None = None, brief: str = "", **_: Any
) -> HarnessResult:
    """The "raw agent" baseline: only checks that something was produced.

    An unchecked LLM agent typically self-evaluates by vibes — "it rendered,
    ship it." That passes even a subtly broken artifact, which is exactly the
    gap colophon's deterministic gates are meant to close.
    """
    produced = bool(document) and (
        "<section" in document
        or "<video" in document
        or "data-centerpiece" in document
    )
    return HarnessResult(
        harness="naive",
        brief=brief,
        passed=produced,
        gates={"produced_output": produced},
        detail="presence-only check (no measurement)",
    )


naive_harness.name = "naive"


class ExternalAgentHarness:
    """Stand-in for a real coding agent (codex/claude/deepseek).

    A row is only ever ``SKIP`` or a real measurement — never a faked result.
    There are two ways to skip, and both say which one it is:

    * the binary is not installed on this machine;
    * the binary is installed but the invocation is not wired yet.

    Neither raises. A benchmark that hard-crashes because a third-party CLI
    happens to be installed on someone's laptop is worse than the gap it is
    trying to measure — it takes every other row down with it.
    """

    def __init__(self, name: str, binary: str) -> None:
        self.name = name
        self.binary = binary

    def _locate(self) -> str | None:
        """Resolve the binary through colophon's effective PATH.

        Not the ambient ``PATH``: that varies with how stripped the sandbox is,
        so the same machine would report "not found" from one shell and
        "installed" from another. ``effective_path`` restores the usual
        Homebrew/local prefixes, making discovery reproducible.
        """
        return shutil.which(self.binary, path=effective_path())

    def _invoke(self, brief: str) -> str:
        """Run the agent on ``brief``; return the document it emitted.

        Integration point: shell out to ``self.binary``, capture its document,
        then hand that to ``colophon_harness``. Deliberately unwired — but
        nothing on the live path calls it, so an unwired harness skips
        honestly instead of exploding.
        """
        raise NotImplementedError(
            f"{self.name}: run {self.binary} on the brief and return its document"
        )

    def __call__(
        self, document: str, *, spec: VideoSpec | None = None, brief: str = "", **_: Any
    ) -> HarnessResult:
        found = self._locate()
        if found is None:
            return HarnessResult(
                harness=self.name,
                brief=brief,
                passed=False,
                skipped=True,
                detail=f"binary {self.binary!r} not found; install it to enable this row",
            )
        return HarnessResult(
            harness=self.name,
            brief=brief,
            passed=False,
            skipped=True,
            detail=(
                f"{self.name}: found {found}, but the invocation is not wired "
                f"yet; implement ExternalAgentHarness._invoke to enable this row"
            ),
        )


def build_matrix(
    briefs: list[tuple[str, str]],
    harnesses: list[Harness],
    *,
    spec: VideoSpec | None = None,
) -> dict[str, Any]:
    """Run every (brief, harness) pair and collect the results."""
    cells: dict[tuple[str, str], HarnessResult] = {}
    for brief_name, document in briefs:
        for h in harnesses:
            cells[(brief_name, h.name)] = h(document, spec=spec, brief=brief_name)
    return {
        "briefs": [b[0] for b in briefs],
        "harnesses": [h.name for h in harnesses],
        "cells": {(b, h): r.to_dict() for (b, h), r in cells.items()},
    }


def format_matrix(report: dict[str, Any]) -> str:
    briefs = report["briefs"]
    harnesses = report["harnesses"]
    cells = report["cells"]
    head = "brief".ljust(22) + "".join(h.ljust(12) for h in harnesses)
    lines = [head, "-" * len(head)]
    for b in briefs:
        row = b.ljust(22)
        for h in harnesses:
            r = cells[(b, h)]
            tag = "SKIP" if r["skipped"] else ("PASS" if r["passed"] else "FAIL")
            row += tag.ljust(12)
        lines.append(row)
    # per-harness pass tally (excluding skips)
    lines.append("")
    for h in harnesses:
        total = sum(1 for b in briefs if not cells[(b, h)]["skipped"])
        passed = sum(
            1 for b in briefs if cells[(b, h)]["passed"] and not cells[(b, h)]["skipped"]
        )
        lines.append(f"{h}: {passed}/{total} briefs passed")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Runnable demonstration. Two briefs (a correct artifact and one with the
# 8px/frame stutter we found in the word-sweep), judged by colophon vs naive,
# plus the external-agent rows wired but skipped.
# --------------------------------------------------------------------------

def _good_doc() -> str:
    return """
    <!doctype html><html><head><style>
    @keyframes word-sweep-in{from{transform:translateY(16px)}to{transform:none}}
    .m-word-sweep .word{display:inline-block;animation-name:word-sweep-in;
      animation-timing-function:cubic-bezier(.2,.75,.34,.94)}
    h1{font-family:sans-serif;font-weight:700}
    @media (prefers-reduced-motion: reduce){.m-word-sweep .word{animation:none}}
    </style></head><body>
    <div data-composition-id="c1" style="background:#0B0B0D">
      <section id="s1" class="clip" style="background:#0B0B0D">
        <h1 data-motion="word-sweep"><span class="word"
          style="animation-delay:0ms;animation-duration:480ms">Ship</span>
          <span class="word"
          style="animation-delay:100ms;animation-duration:480ms">it</span></h1>
      </section>
    </div></body></html>
    """


def _broken_doc() -> str:
    """Identical to the good doc, but the word-sweep travels only 8px.

    At 30fps that is 8px / 14.4f = 0.56px/frame — under the 1px/frame floor,
    so it stutters. colophon's gate 12 must catch this; a naive agent won't.
    """
    return """
    <!doctype html><html><head><style>
    @keyframes word-sweep-in{from{transform:translateY(8px)}to{transform:none}}
    .m-word-sweep .word{display:inline-block;animation-name:word-sweep-in;
      animation-timing-function:cubic-bezier(.2,.75,.34,.94)}
    h1{font-family:sans-serif;font-weight:700}
    @media (prefers-reduced-motion: reduce){.m-word-sweep .word{animation:none}}
    </style></head><body>
    <div data-composition-id="c1" style="background:#0B0B0D">
      <section id="s1" class="clip" style="background:#0B0B0D">
        <h1 data-motion="word-sweep"><span class="word"
          style="animation-delay:0ms;animation-duration:480ms">Ship</span>
          <span class="word"
          style="animation-delay:100ms;animation-duration:480ms">it</span></h1>
      </section>
    </div></body></html>
    """


def run_matrix_demo(spec: VideoSpec | None = None) -> dict[str, Any]:
    briefs = [("good_artifact", _good_doc()), ("broken_stutter", _broken_doc())]
    harnesses: list[Harness] = [
        colophon_harness,
        naive_harness,
        ExternalAgentHarness("codex", "codex"),
        ExternalAgentHarness("claude", "claude"),
        ExternalAgentHarness("deepseek", "dsh"),
    ]
    return build_matrix(briefs, harnesses, spec=spec)


def _main() -> None:
    report = run_matrix_demo()
    print(format_matrix(report))
    print()
    # The thesis, stated as a check:
    cells = report["cells"]
    colophon_good = cells[("good_artifact", "colophon")]["passed"]
    colophon_broken = cells[("broken_stutter", "colophon")]["passed"]
    naive_broken = cells[("broken_stutter", "naive")]["passed"]
    print(
        "thesis check: colophon passes good"
        f" ({colophon_good}) and fails the stutter ({not colophon_broken});"
        f" naive passes the stutter ({naive_broken}) -> colophon measures,"
        " naive guesses."
    )


if __name__ == "__main__":
    _main()
