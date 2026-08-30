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

Real agents (``codex``, ``claude``) are wired through :mod:`colophon.bench.agents`,
but they only run when you ask for them — see :class:`ExternalAgentHarness`. The
default matrix stays cheap, offline and reproducible; the live rows are the
expensive, non-reproducible ones you opt into on purpose.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..qa.runner import run_stages
from ..qa.stages import motion_velocity as motion_velocity_stage
from ..qa.stages import static as static_stage
from ..qa.stages import taste as taste_stage
from ..runtime.tools import effective_path
from ..spec.schema import VideoSpec
from .agents import (
    DEFAULT_AGENT_TIMEOUT_S,
    AgentAttempt,
    AgentProfile,
    profile_for,
    run_agent_for_brief,
)

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
    #: Present only for rows backed by a live agent. It is the whole audit
    #: trail — argv, exit code, workdir, timing, and how much came back —
    #: because a live row is not reproducible and the record is the only way to
    #: argue about it later.
    attempt: dict[str, Any] | None = None

    @property
    def live_agent(self) -> bool:
        """True when this row came from really running an agent.

        Flagged because such a row is not reproducible: the same command can
        score differently tomorrow. Anything with this set should be read as
        "what happened on this run", never as a stable number.
        """
        return self.attempt is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "harness": self.harness,
            "brief": self.brief,
            "passed": self.passed,
            "skipped": self.skipped,
            "gates": dict(self.gates),
            "detail": self.detail,
            "live_agent": self.live_agent,
            "attempt": self.attempt,
        }


#: A harness is a callable:
#: (document, *, spec=None, brief="", task="") -> HarnessResult,
#: and carries a ``.name`` attribute.
#:
#: ``document`` is the reference artifact for the deterministic rows. An
#: external-agent row ignores it — it generates its own artifact from ``task``
#: and judges that, which is the only way the comparison means anything.
Harness = Callable[..., HarnessResult]


@dataclass(frozen=True)
class BenchBrief:
    """One column of the matrix: what we ask for, plus a reference artifact.

    Two texts, because the rows use them differently:

    * ``prompt`` is the task handed to an external agent. It has to read like a
      real instruction, or we would be measuring how well an agent guesses.
    * ``document`` is the reference artifact the deterministic rows judge. Those
      rows are the control group — the whole point is that we know the right
      answer for them in advance.
    """

    name: str
    prompt: str
    document: str = ""


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
    """A real coding agent (codex/claude/…), measured by colophon's own gates.

    The invocation is genuinely wired — this is not a placeholder. It is
    *opt-in*, which is a different thing, and the distinction matters:

    ==========================  ==========================================
    state                        row
    ==========================  ==========================================
    binary not installed         SKIP "not found"
    installed, not enabled       SKIP "found, but real runs are opt-in"
    enabled, agent produced      real measurement (PASS/FAIL)
    enabled, agent failed        SKIP with the reason it failed
    ==========================  ==========================================

    Why opt-in rather than automatic: running a coding agent costs money, needs
    network and credentials, takes minutes, and is not reproducible. A
    benchmark that quietly shells out to a paid API because someone happened to
    have the binary installed is not a benchmark, it is a surprise bill. So the
    default matrix stays free, offline and byte-for-byte repeatable, and the
    live rows are something you switch on deliberately.

    And why an agent that *failed to produce anything* is SKIP rather than FAIL:
    "codex scored 0/2" reads as a verdict on codex. "codex never ran — no
    network" is the truth. Conflating them is exactly the kind of number this
    whole matrix exists to avoid publishing.
    """

    def __init__(
        self,
        name: str,
        binary: str,
        *,
        profile: AgentProfile | None = None,
        enabled: bool = False,
        timeout_s: int = DEFAULT_AGENT_TIMEOUT_S,
        workdir: Path | None = None,
        extra_args: list[str] | None = None,
        judge: Harness | None = None,
    ) -> None:
        self.name = name
        self.binary = binary
        self.profile = profile or profile_for(name, binary)
        self.enabled = enabled
        self.timeout_s = timeout_s
        self.workdir = workdir
        self.extra_args = extra_args
        # Judged by colophon's own gates, not by the agent's opinion of itself.
        # An agent grading its own homework is the baseline we are measuring
        # against, not the measurement.
        self._judge = judge or colophon_harness

    def _locate(self) -> str | None:
        """Resolve the binary through colophon's effective PATH.

        Not the ambient ``PATH``: that varies with how stripped the sandbox is,
        so the same machine would report "not found" from one shell and
        "installed" from another. ``effective_path`` restores the usual
        Homebrew/local prefixes, making discovery reproducible.
        """
        return shutil.which(self.binary, path=effective_path())

    def _invoke(self, task: str, *, spec: VideoSpec | None = None) -> AgentAttempt:
        """Really run the agent on ``task`` and read back what it produced.

        Never raises. Every failure — timeout, missing credentials, an agent
        that philosophised instead of writing a file — comes back as an
        :class:`AgentAttempt` carrying the reason, so the row can report it
        instead of the matrix crashing or inventing a score.
        """
        return run_agent_for_brief(
            self.profile,
            task,
            spec=spec,
            timeout_s=self.timeout_s,
            workdir=self.workdir,
            extra_args=self.extra_args,
        )

    def __call__(
        self,
        document: str,
        *,
        spec: VideoSpec | None = None,
        brief: str = "",
        task: str = "",
        **_: Any,
    ) -> HarnessResult:
        """Score this agent on one brief.

        ``document`` is ignored on purpose. It is the reference artifact for
        the deterministic rows; this harness is supposed to make its own, and
        scoring it on someone else's artifact would tell us nothing.
        """
        found = self._locate()
        if found is None:
            return HarnessResult(
                harness=self.name,
                brief=brief,
                passed=False,
                skipped=True,
                detail=f"binary {self.binary!r} not found; install it to enable this row",
            )
        if not self.enabled:
            return HarnessResult(
                harness=self.name,
                brief=brief,
                passed=False,
                skipped=True,
                detail=(
                    f"{self.name}: found {found}; real runs are opt-in "
                    f"(enable with --agents) because they cost money, need "
                    f"network, and are not reproducible"
                ),
            )

        attempt = self._invoke(task or brief, spec=spec)
        if not attempt.ok:
            return HarnessResult(
                harness=self.name,
                brief=brief,
                passed=False,
                skipped=True,
                detail=f"{self.name}: {attempt.invocation.error}",
                attempt=attempt.to_dict(),
            )

        judged = self._judge(attempt.document, spec=spec, brief=brief)
        seconds = attempt.invocation.duration_s
        return HarnessResult(
            harness=self.name,
            brief=brief,
            passed=judged.passed,
            gates=judged.gates,
            skipped=False,
            detail=(
                f"{self.name}: produced {len(attempt.document)} chars in "
                f"{seconds:.1f}s, judged by colophon's artifact gates"
            ),
            attempt=attempt.to_dict(),
        )


#: Which external agents the matrix rows cover. ``deepseek``/``dsh`` is kept in
#: the list on purpose: it is not installed here, so the demo exercises the
#: "binary not found" state alongside "installed but not enabled" — otherwise
#: one of the two skip paths would never appear in a real run.
DEFAULT_EXTERNAL_AGENTS: tuple[tuple[str, str], ...] = (
    ("codex", "codex"),
    ("claude", "claude"),
    ("deepseek", "dsh"),
)


def external_harnesses(
    *,
    enabled: bool = False,
    timeout_s: int = DEFAULT_AGENT_TIMEOUT_S,
    workdir: Path | None = None,
    names: tuple[tuple[str, str], ...] = DEFAULT_EXTERNAL_AGENTS,
) -> list[Harness]:
    """Build the external-agent rows, all sharing one opt-in decision.

    Kept as a factory so "run the live agents" is a single switch rather than a
    flag the caller has to remember to thread into three constructors.
    """
    return [
        ExternalAgentHarness(
            name,
            binary,
            enabled=enabled,
            timeout_s=timeout_s,
            workdir=workdir,
        )
        for name, binary in names
    ]


def build_matrix(
    briefs: list[BenchBrief],
    harnesses: list[Harness],
    *,
    spec: VideoSpec | None = None,
) -> dict[str, Any]:
    """Run every (brief, harness) pair and collect the results."""
    cells: dict[tuple[str, str], HarnessResult] = {}
    for brief in briefs:
        for h in harnesses:
            cells[(brief.name, h.name)] = h(
                brief.document, spec=spec, brief=brief.name, task=brief.prompt
            )
    return {
        "briefs": [b.name for b in briefs],
        "harnesses": [h.name for h in harnesses],
        "cells": {(b, h): r.to_dict() for (b, h), r in cells.items()},
    }


#: Separates brief from harness in a flattened cell key. "::" rather than a
#: single character because brief names contain spaces and hyphens, and a
#: reader should be able to see where the split is.
CELL_KEY_SEPARATOR = "::"


def json_safe(report: dict[str, Any]) -> dict[str, Any]:
    """Flatten the (brief, harness) tuple keys so the report serialises.

    Tuples are the right key in memory — ``cells[("good_artifact", "colophon")]``
    is exactly how you want to read a matrix in Python — but ``json.dumps``
    refuses them, and duct-taping ``default=str`` over that would silently
    stringify every key into ``"('good_artifact', 'colophon')"``. Better to do
    the flattening once, here, where the shape is defined.
    """
    return {
        **report,
        "cells": {
            f"{b}{CELL_KEY_SEPARATOR}{h}": r for (b, h), r in report["cells"].items()
        },
    }


def format_matrix(report: dict[str, Any]) -> str:
    briefs = report["briefs"]
    harnesses = report["harnesses"]
    cells = report["cells"]
    head = "brief".ljust(22) + "".join(h.ljust(12) for h in harnesses)
    lines = [head, "-" * len(head)]
    any_live = False
    for b in briefs:
        row = b.ljust(22)
        for h in harnesses:
            r = cells[(b, h)]
            tag = "SKIP" if r["skipped"] else ("PASS" if r["passed"] else "FAIL")
            # Mark only the live rows that actually *measured* something. A
            # live row that failed to produce an artifact is already explained
            # in the skip list below, and flagging it too would make "*" mean
            # two different things ("scored" and "attempted") in one table.
            if r.get("live_agent") and not r["skipped"]:
                tag += "*"
                any_live = True
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
    if any_live:
        lines.append("")
        lines.append(
            "* live agent run: a real measurement of one real attempt, not a"
        )
        lines.append("  reproducible number. The same command can score differently.")
    # Why each row was skipped, so a wall of SKIPs is still informative.
    reasons: dict[str, str] = {}
    for b in briefs:
        for h in harnesses:
            r = cells[(b, h)]
            if r["skipped"] and r["detail"]:
                reasons.setdefault(h, r["detail"])
    if reasons:
        lines.append("")
        for h in harnesses:
            if h in reasons:
                lines.append(f"skip: {h}: {reasons[h]}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Runnable demonstration. Two briefs (a correct artifact and one with the
# 8px/frame stutter we found in the word-sweep), judged by colophon vs naive,
# plus the external-agent rows — really wired, but opt-in so the default run
# stays free and reproducible.
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


#: The task text every external agent sees. Both demo briefs share it because
#: the point of the external rows is "can this agent produce something our
#: gates accept at all", not "can it follow subtly different instructions".
DEMO_PROMPT = (
    "A dark product-launch title card: the words 'Ship it' sweep up into "
    "place, one word at a time."
)


def demo_briefs() -> list[BenchBrief]:
    """The control group: one artifact we know is good, one we know stutters.

    These two exist so the deterministic rows can be checked against a known
    answer. If colophon's gates ever pass ``broken_stutter``, the instrument is
    broken — and that is visible immediately instead of being discovered later
    as a mysterious green row.
    """
    return [
        BenchBrief(
            name="good_artifact",
            prompt=DEMO_PROMPT,
            document=_good_doc(),
        ),
        BenchBrief(
            name="broken_stutter",
            prompt=DEMO_PROMPT,
            document=_broken_doc(),
        ),
    ]


def run_matrix_demo(
    spec: VideoSpec | None = None,
    *,
    agents: bool = False,
    timeout_s: int = DEFAULT_AGENT_TIMEOUT_S,
    workdir: Path | None = None,
) -> dict[str, Any]:
    """Run the demonstration matrix.

    With ``agents=False`` (the default) nothing leaves the machine: no network,
    no spend, byte-for-byte repeatable. With ``agents=True`` the external rows
    really call codex/claude and are marked ``*`` in the output.
    """
    harnesses: list[Harness] = [
        colophon_harness,
        naive_harness,
        *external_harnesses(enabled=agents, timeout_s=timeout_s, workdir=workdir),
    ]
    return build_matrix(demo_briefs(), harnesses, spec=spec)


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
