"""Running a real coding agent, so the bench can measure someone else's output.

This is the piece that turns the external rows of the matrix from "SKIP" into a
real measurement. Three rules shape everything below, and they are the reason
this module is longer than "just call subprocess":

1. **Opt-in, never ambient.** Invoking a coding agent costs money, takes
   minutes, needs network and credentials, and is not reproducible. A benchmark
   that quietly shells out to a paid API because someone happened to have the
   binary installed is not a benchmark — it is a surprise bill. So every caller
   must ask for it explicitly.

2. **A failure is a result, not a crash.** Missing binary, expired login, no
   network, timeout, or an agent that produced nothing: each of those is a
   legitimate observation about the world and each is reported as a row with a
   plain-language reason. Nothing here raises past its caller.

3. **Never invent a number.** If we did not get a document out of the agent, we
   do not score one. The matrix would rather show an honest gap than a
   fabricated cell.

Everything here is a leaf: deleting this file (or the whole ``bench`` package)
must leave the rest of colophon working.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from ..runtime.tools import effective_path

#: How long we let a real agent run before giving up. Generous on purpose: an
#: agent that has to think about layout then write a file can legitimately take
#: a couple of minutes, and a timeout that is too tight makes every row fail
#: for a reason that has nothing to do with quality.
DEFAULT_AGENT_TIMEOUT_S = 600

#: How much of an agent's chatter to keep. Enough to explain a failure, not
#: enough to bloat a report — agent stdout can run to megabytes.
OUTPUT_TAIL_CHARS = 2000


class AgentInvocationError(RuntimeError):
    """Raised only by :func:`invoke_agent` internals; callers catch it.

    Kept as an exception rather than a return value so the "what went wrong"
    path reads naturally, but it never escapes :func:`invoke_agent`.
    """


@dataclass(frozen=True)
class AgentInvocation:
    """The record of one attempt to make an agent produce an artifact.

    Carries the argv as well as the outcome, because "which flags did we use"
    is exactly the question someone asks when a row looks wrong. A bench result
    you cannot reproduce is a bench result you cannot argue with.
    """

    name: str
    binary: str
    argv: tuple[str, ...]
    workdir: str
    exit_code: int | None = None
    duration_s: float = 0.0
    document_path: str | None = None
    error: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""

    @property
    def produced_document(self) -> bool:
        return self.document_path is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "binary": self.binary,
            "argv": list(self.argv),
            "workdir": self.workdir,
            "exit_code": self.exit_code,
            "duration_s": round(self.duration_s, 3),
            "document_path": self.document_path,
            "error": self.error,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "produced_document": self.produced_document,
        }


class AgentProfile(Protocol):
    """How to turn a task into an argv for one particular agent CLI.

    A Protocol rather than an ABC because the built-ins differ only in their
    flags, and a caller who wants to add a new agent should be able to pass a
    plain function without importing anything from here.
    """

    name: str
    binary: str

    def build_argv(self, prompt: str, workdir: Path) -> list[str]: ...


def _tail(text: str) -> str:
    return text[-OUTPUT_TAIL_CHARS:] if len(text) > OUTPUT_TAIL_CHARS else text


def _resolve(binary: str) -> str | None:
    """Find ``binary`` on the *effective* PATH, not the ambient one.

    The sandbox PATH omits Homebrew prefixes, so the same machine would report
    "not installed" from one shell and "installed" from another. Resolving
    through ``effective_path`` makes discovery reproducible.
    """
    return shutil.which(binary, path=effective_path())


def collect_document(workdir: Path) -> Path | None:
    """Find the HTML artifact an agent left in ``workdir``.

    Agents are instructed to write ``index.html``, but they don't always
    comply, and refusing to score an artifact because it is named ``scene.html``
    would be measuring filename discipline rather than output quality. So we
    look for ``index.html`` first, then fall back to the largest ``.html`` file
    in the tree — largest is a decent proxy for the real artifact over a stub
    or an empty scaffold.

    Deterministic: ties on size are broken by path so the same tree always
    yields the same answer.
    """
    index = workdir / "index.html"
    if index.is_file() and index.stat().st_size > 0:
        return index

    candidates = [
        p
        for p in workdir.rglob("*.html")
        if p.is_file() and p.stat().st_size > 0 and "node_modules" not in p.parts
    ]
    candidates += [
        p
        for p in workdir.rglob("*.htm")
        if p.is_file() and p.stat().st_size > 0 and "node_modules" not in p.parts
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p.stat().st_size, str(p)))


def invoke_agent(
    profile: AgentProfile,
    prompt: str,
    *,
    workdir: Path | None = None,
    timeout_s: int = DEFAULT_AGENT_TIMEOUT_S,
    extra_args: list[str] | None = None,
    keep_workdir: bool = True,
) -> AgentInvocation:
    """Run one agent on one prompt. Never raises; reports failure instead.

    The agent runs with ``workdir`` as its current directory, which is also how
    we scope the blast radius: whatever it writes lands in a scratch directory
    we can name in the report, not in the user's project.
    """
    binary = _resolve(profile.binary)
    if binary is None:
        return AgentInvocation(
            name=profile.name,
            binary=profile.binary,
            argv=(),
            workdir=str(workdir) if workdir else "",
            error=f"binary {profile.binary!r} not found on PATH",
        )

    owns_workdir = workdir is None
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix=f"colophon-bench-{profile.name}-"))
    workdir.mkdir(parents=True, exist_ok=True)

    argv = profile.build_argv(prompt, workdir)
    if extra_args:
        argv = [*argv, *extra_args]

    started = time.monotonic()
    code: int | None = None
    out = err = ""
    error = ""
    try:
        proc = subprocess.run(
            [str(a) for a in argv],
            cwd=str(workdir),
            env={"PATH": effective_path(), **_passthrough_env()},
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        code = proc.returncode
        out, err = proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        error = f"timed out after {timeout_s}s"
    except OSError as exc:
        # Covers a binary that exists but cannot be executed (bad arch, broken
        # symlink, not signed) — the common case is a stale Homebrew link.
        error = f"could not execute {binary}: {exc}"
    duration = time.monotonic() - started

    document = collect_document(workdir)
    if not error and document is None:
        error = f"agent finished (exit {code}) but left no HTML in {workdir}"
    if not error and code not in (0, None):
        # Non-zero exit with a document in hand is still worth scoring: several
        # agents exit non-zero on a benign trailing warning. We note it and
        # keep the artifact rather than throwing away a real measurement.
        error = ""

    invocation = AgentInvocation(
        name=profile.name,
        binary=profile.binary,
        argv=tuple(str(a) for a in argv),
        workdir=str(workdir),
        exit_code=code,
        duration_s=duration,
        document_path=str(document) if document else None,
        error=error,
        stdout_tail=_tail(out),
        stderr_tail=_tail(err),
    )
    if not keep_workdir and owns_workdir:
        shutil.rmtree(workdir, ignore_errors=True)
    return invocation


def _passthrough_env() -> dict[str, str]:
    """Environment variables an agent genuinely needs to function.

    Deliberately narrow. An agent CLI needs a HOME (credentials, config) and a
    PATH (already set), and it needs to know it is not talking to a terminal so
    it does not emit interactive prompts or colour codes. Everything else the
    parent had is noise that only makes runs harder to reproduce.
    """
    import os

    keep = ("HOME", "USER", "SHELL", "TERM", "LANG", "LC_ALL", "TMPDIR")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["CI"] = "1"
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    return env


# --------------------------------------------------------------------------
# Built-in profiles.
#
# Flag choices are the narrowest set that lets the agent write a file without
# a human present. Anything broader (full disk access, bypassed approvals) is
# left to the caller via ``extra_args`` so the dangerous choice is always a
# visible, deliberate one in the caller's own code.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CodexProfile:
    """``codex exec`` — the non-interactive subcommand.

    * ``--skip-git-repo-check``: the bench runs in a temp directory that is not
      a git repo, and codex refuses to start outside one by default.
    * ``--ephemeral``: no session is written to the user's history. A benchmark
      should not leave 200 entries in someone's session picker.
    * ``-s workspace-write``: the agent may write inside the cwd (which is the
      scratch dir) and nowhere else. Read-only would make it produce nothing.
    """

    name: str = "codex"
    binary: str = "codex"

    def build_argv(self, prompt: str, workdir: Path) -> list[str]:
        return [
            self.binary,
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "-s",
            "workspace-write",
            prompt,
        ]


@dataclass(frozen=True)
class ClaudeProfile:
    """``claude -p`` — print mode, which is the non-interactive path.

    * ``-p``: run one prompt, print, exit. Also skips the workspace-trust
      dialog, which matters because nobody is there to click it.
    * ``--permission-mode acceptEdits``: allow file writes without a prompt,
      but keep the rest of the permission model intact. Chosen over
      ``bypassPermissions`` — the agent needs to write a file, not to do
      whatever it likes.
    * ``--allowedTools``: the minimum tool set for "write an HTML file".
    """

    name: str = "claude"
    binary: str = "claude"

    def build_argv(self, prompt: str, workdir: Path) -> list[str]:
        return [
            self.binary,
            "-p",
            "--permission-mode",
            "acceptEdits",
            "--allowedTools",
            "Write",
            "Edit",
            prompt,
        ]


@dataclass(frozen=True)
class GenericProfile:
    """Any agent CLI that takes a prompt as its final argument.

    Exists so a new agent can be added from a config file or the CLI without
    touching this module. It makes no promises about sandboxing — that is the
    caller's business.
    """

    name: str
    binary: str
    prefix_args: tuple[str, ...] = ()

    def build_argv(self, prompt: str, workdir: Path) -> list[str]:
        return [self.binary, *self.prefix_args, prompt]


#: The agents we know how to drive, in the order the matrix shows them.
BUILTIN_PROFILES: tuple[AgentProfile, ...] = (
    CodexProfile(),
    ClaudeProfile(),
)


def profile_for(name: str, binary: str | None = None) -> AgentProfile:
    """Look up a built-in profile by name, else fall back to a generic one."""
    for profile in BUILTIN_PROFILES:
        if profile.name == name:
            return profile
    return GenericProfile(name=name, binary=binary or name)


def build_prompt(brief: str, spec_context: str | None = None) -> str:
    """The task we hand the agent.

    Written to be unambiguous about the deliverable, because "make me a video
    scene" invites an agent to write a React app, a markdown plan, or an
    apology. Naming the exact filename and forbidding external assets keeps the
    output measurable by colophon's gates.
    """
    lines = [
        "Produce one self-contained HTML artifact for a short animated video scene.",
        "",
        f"Scene brief: {brief}",
        "",
        "Requirements:",
        '- Write exactly one file named "index.html" in the current directory.',
        "- It must be a complete HTML document with inline <style>.",
        "- No external assets: no CDN links, no web fonts, no remote images.",
        "- Wrap the composition in a <div data-composition-id=\"c1\">.",
        "- Each scene is a <section class=\"clip\" id=\"s1\">.",
        "- Respect prefers-reduced-motion by disabling animation under it.",
        "- Keep every text string short and concrete.",
        "",
        "Write the file. Do not describe what you would write.",
    ]
    if spec_context:
        lines += ["", "Spec context (text marked as a claim is the only copy you may use):", spec_context]
    return "\n".join(lines)


def spec_context_for(spec: Any) -> str | None:
    """Render a spec as prompt text, or ``None`` if the bridge is unavailable.

    Imported lazily and defensively: the agent bridge is an optional leaf that
    colophon must run without, so the bench may not depend on it at import
    time. If it is gone, the bench still runs — it just prompts with less
    context.
    """
    if spec is None:
        return None
    try:
        from ..adapters.agent.bridge import spec_to_prompt_context
    except ImportError:
        return None
    try:
        return spec_to_prompt_context(spec)
    except Exception:  # noqa: BLE001 - context is a nicety, never a failure
        return None


@dataclass
class AgentAttempt:
    """An agent invocation paired with the document it produced, if any."""

    invocation: AgentInvocation
    document: str = ""

    @property
    def ok(self) -> bool:
        return self.invocation.produced_document and bool(self.document)

    def to_dict(self) -> dict[str, Any]:
        payload = self.invocation.to_dict()
        payload["document_chars"] = len(self.document)
        return payload


def run_agent_for_brief(
    profile: AgentProfile,
    brief: str,
    *,
    spec: Any = None,
    timeout_s: int = DEFAULT_AGENT_TIMEOUT_S,
    workdir: Path | None = None,
    extra_args: list[str] | None = None,
) -> AgentAttempt:
    """Invoke one agent on one brief and read back whatever it wrote."""
    prompt = build_prompt(brief, spec_context_for(spec))
    invocation = invoke_agent(
        profile,
        prompt,
        workdir=workdir,
        timeout_s=timeout_s,
        extra_args=extra_args,
    )
    if not invocation.produced_document:
        return AgentAttempt(invocation=invocation)
    try:
        document = Path(str(invocation.document_path)).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        # ``replace`` rather than rebuilding from ``to_dict()``: the dict
        # carries derived keys (produced_document) that the frozen record does
        # not accept as inputs, so round-tripping through it would raise.
        invocation = replace(
            invocation, error=f"could not read {invocation.document_path}: {exc}"
        )
        return AgentAttempt(invocation=invocation)
    return AgentAttempt(invocation=invocation, document=document)
