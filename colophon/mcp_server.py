"""Colophon as a set of MCP tools, so an agent harness can drive it.

Plain English
=============

Colophon is a *gate spine*: it inspects a video spec and the things made from
it, and reports exactly what is wrong. On its own it never guesses and never
fixes taste. That makes it a good instrument and a poor employee — it needs
something outside it to read the report and act on it.

This module is the socket that thing plugs into. It exposes the pipeline as
MCP (Model Context Protocol) tools over HTTP, so an agent harness — TrueForge,
in our case — can hand its agent the gates and let the agent do the real work:

    read the spec  ->  run the gates  ->  read the blockers  ->  edit
                   ->  run the gates again  ->  repeat until ready

That loop is the point. The agent is not calling a model to ask "is this
video good?"; it is calling a deterministic instrument, reading a precise
answer, and acting on it. The harness supplies the loop, the tools, the
sandbox and the session state. Colophon supplies the ground truth.

Why HTTP and not stdio
======================

TrueForge's MCP client only speaks to *remote* (HTTP) servers — its server
type enum has no stdio variant, so there is no ``command`` to spawn. That is
the whole reason for the transport choice here; nothing about the tools
themselves cares.

Read-only hints
===============

None of these tools carry annotations, on purpose. TrueForge's default
approval list is ``["@write", "@destructive"]`` and *unannotated tools are
exempt* from prompting, so leaving them unannotated keeps an agent from
stalling on a permission prompt mid-loop. The tools that really do write
(``colophon_init``, ``colophon_plan``, ``colophon_qa``, ``colophon_design``)
are documented as writing in their descriptions instead.

That exemption is exactly why the paths need containing here rather than at
the prompt: an exempt tool is one no human is asked about, so nothing stands
between a caller naming ``/etc`` and this process writing there. Every path a
tool accepts is therefore confined to a root configured when the server
starts — see :mod:`colophon.sandbox`. Used as a library, with no root
configured, nothing is confined; there is no deputy to confuse.

Shape of every answer
=====================

Every tool returns a JSON object with ``ok`` first. On success that is
``True`` and the payload follows; on failure it is ``False`` and there is an
``error`` string and nothing else is promised. On success there is also:

* ``state``     — ``blocked`` / ``ready_with_warnings`` / ``ready``
* ``blockers``  — ``[{stage, code, message}]``, the things that must be fixed
* ``warnings``  — advisory findings
* ``hint``      — what to do next, in one sentence

The hint exists because of a specific failure mode: several gates report
"nothing to check" before an artifact exists, and the taxonomy counts that as
a blocker (failing closed is correct). An agent that doesn't know this reads
the blocker as a defect it caused and starts "fixing" a spec that was fine.
The hint says out loud what a human would have inferred.
"""

from __future__ import annotations

import argparse
import functools
import json
from pathlib import Path
from typing import Any, Callable

from . import sandbox
from .harness import designer as harness_designer
from .presentation.normalize import normalize
from .qa import pipeline as qa_pipeline
from .qa import taxonomy as taxonomy
from .qa.runner import run_stages
from .runs import layout as run_layout
from .runs import manifest as run_manifest
from .runtime import tools
from .spec.hash import spec_sha256
from .spec.io import load as load_spec
from .spec.io import save as save_spec
from .spec.io import write_json
from .spec.schema import VideoSpec
from .timeline.plan import build_plan

DEFAULT_RENDERER = "hyperframes"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_PATH = "/mcp"

#: Environment variable holding the bearer token clients must present. Needed
#: to bind anywhere but loopback, and honoured on loopback too when set.
TOKEN_ENV = "COLOPHON_MCP_TOKEN"

#: A finding message longer than this is truncated. Gate messages are meant to
#: be read by an agent with a context budget, and the tail is rarely the part
#: that says what to fix.
MAX_MESSAGE_CHARS = 300

#: Cap on how many findings of each kind a tool returns. Fourteen gates cannot
#: produce more than this in practice; the cap is here so a pathological spec
#: cannot blow up an agent's context.
MAX_FINDINGS = 40

INSTRUCTIONS = """\
Colophon turns a video spec into a verdict you can act on.

Start with `colophon_gates` to see what the fourteen gates check and what each
one needs before it can tell the truth. Then loop:

    colophon_init      freeze a spec into a run
    colophon_validate  run the four spec-level gates (no artifacts needed)
    colophon_qa        run all fourteen gates on an emitted/rendered attempt

A verdict is `blocked`, `ready_with_warnings`, or `ready`. Fix what the
blockers name, re-run, repeat. Read the `hint` before acting on a blocker:
before an artifact exists several gates report "nothing to check", and colophon
counts that as a blocker on purpose rather than passing on silence.
"""


# --------------------------------------------------------------------------
# Rendering a verdict
# --------------------------------------------------------------------------


def _clip(text: str) -> str:
    text = str(text)
    return text if len(text) <= MAX_MESSAGE_CHARS else text[: MAX_MESSAGE_CHARS - 1] + "…"


def _finding(finding: Any) -> dict[str, Any]:
    """One finding, in the shape an agent can act on.

    ``code`` is ``None`` when the taxonomy has not been taught to name this
    failure yet. That is not a missing field — it is the fails-closed rule
    made visible: an unnamed finding blocks rather than passes, and the agent
    should treat ``None`` as "colophon cannot classify this, so it cannot be
    mechanically fixed" rather than as "no problem".
    """
    return {
        "stage": finding.stage_id,
        "code": finding.code,
        "message": _clip(finding.message),
    }


def _verdict(
    result: Any,
    *,
    has_project: bool,
    has_video: bool,
    scope: str = "full",
) -> dict[str, Any]:
    """Turn a pipeline result into the answer shape every tool shares.

    ``scope`` says which gate set ran, and it decides what the hint is allowed
    to claim. ``"spec"`` means only the four spec-level gates ran, so a missing
    artifact can never be the cause of a blocker — and blaming one would send
    the agent off to emit something when the real problem is in the spec.
    ``"full"`` means the artifact-dependent gates ran too, so "nothing to
    check" is a live possibility and worth explaining.
    """
    assessment = taxonomy.assess(result.results)
    return {
        "state": assessment.state,
        "spec_sha256": result.spec_sha256,
        "gates_run": len(result.results),
        "gates_passed": sum(1 for r in result.results if r.passed),
        "blockers": [_finding(f) for f in assessment.blockers[:MAX_FINDINGS]],
        "warnings": [_finding(f) for f in assessment.warnings[:MAX_FINDINGS]],
        "stages": [
            {
                "stage": r.stage_id,
                "passed": r.passed,
                "advisory": r.advisory,
                "problems": [_clip(p) for p in r.problems[:MAX_FINDINGS]],
            }
            for r in result.results
        ],
        "hint": _hint(
            assessment,
            has_project=has_project,
            has_video=has_video,
            scope=scope,
        ),
    }


def _hint(
    assessment: Any, *, has_project: bool, has_video: bool, scope: str = "full"
) -> str:
    """The one sentence a human would have inferred for themselves."""
    if not assessment.blockers:
        if assessment.warnings:
            return "no blockers; the warnings above are advisory, not defects"
        return "no blockers; this is ready at the level the gates were able to check"
    if scope == "spec":
        # Only spec-level gates ran, so every blocker here is a real defect in
        # the spec. There is no missing-artifact explanation to offer, and
        # inventing one would point the agent at the wrong problem.
        return "fix the blockers named above, then re-run this gate to confirm"
    if not has_project:
        return (
            "nothing has been emitted yet, so the project- and video-tier gates "
            "are reporting 'nothing to check' — that is a blocker by design, not "
            "a defect you introduced; emit the project and re-run"
        )
    if not has_video:
        return (
            "the project is emitted but no MP4 exists yet, so the video-tier "
            "gates are reporting 'nothing to check' — that is a blocker by "
            "design; render and re-run before treating it as a defect"
        )
    return "fix the blockers named above, then re-run this gate to confirm"


# --------------------------------------------------------------------------
# Tools (plain functions; registered with the MCP server further down)
# --------------------------------------------------------------------------


def gates() -> dict[str, Any]:
    """List every gate, what it checks, and what it needs before it can run."""
    fns = qa_pipeline.full_gate_fns()
    catalog = qa_pipeline.gate_catalog(fns)
    spec_level = {fn.__name__ for fn in qa_pipeline.spec_gate_fns()}
    return {
        "ok": True,
        "gate_count": len(catalog),
        "gates": [
            {
                **info.to_dict(),
                "spec_level": info.stage_id in spec_level,
            }
            for info in catalog
        ],
        "tiers": {
            "spec": "runs on the spec and the timeline plan alone",
            "project": "needs the emitted HTML/CSS project",
            "video": "needs the encoded MP4",
        },
        "note": (
            "a gate that reports 'nothing to check' is blocking on purpose: "
            "colophon fails closed rather than passing on silence"
        ),
    }


def doctor() -> dict[str, Any]:
    """Check whether the runtime this machine needs is present."""
    found = tools.resolve_runtime()
    return {
        "ok": True,
        "ready": all(t.found for t in found.values()),
        "tools": {
            name: {
                "found": t.found,
                "version": t.version,
                "path": str(t.path) if t.path else None,
            }
            for name, t in sorted(found.items())
        },
        "cache_key": tools.cache_key(found),
    }


def init_run(spec_path: str, run_dir: str) -> dict[str, Any]:
    """Freeze a spec into a new run directory (writes to that directory).

    Normalizes the spec first, so the copy in the run directory is the one the
    gates will actually be reading — not necessarily byte-identical to the file
    you passed in.
    """
    spec = load_spec(sandbox.within(spec_path, label="spec_path"))
    spec, log = normalize(spec)
    paths = run_layout.init_run(sandbox.within(run_dir, label="run_dir"), spec)
    write_json(
        {"tools": {k: v.to_dict() for k, v in tools.resolve_runtime().items()}},
        paths.runtime_state,
    )
    return {
        "ok": True,
        "run_dir": str(paths.root),
        "spec_sha256": spec_sha256(spec),
        "scene_count": len(spec.scenes),
        "claim_count": len(spec.claims),
        "normalize_notes": [
            f"{e['scene_id']} {e['action']} {e['detail']}" for e in log.entries
        ][:MAX_FINDINGS],
    }


def validate(run_dir: str) -> dict[str, Any]:
    """Run the four spec-level gates. Needs no emitted project and no video."""
    paths = run_layout.run_paths(sandbox.within(run_dir, label="run_dir"))
    if not paths.spec.is_file():
        raise FileNotFoundError(f"no spec at {paths.spec}; run colophon_init first")
    spec = load_spec(paths.spec)
    normalized, plan, _ = _plan_for(spec)
    result = run_stages(
        qa_pipeline.spec_gate_fns(),
        {"spec": normalized, "plan": plan},
        spec_sha256=spec_sha256(normalized),
    )
    # scope="spec": these four gates never read an artifact, so a blocker here
    # is always a defect in the spec. Without it the hint would blame a missing
    # project and send the agent off to emit, when the spec is what is wrong.
    verdict = _verdict(result, has_project=False, has_video=False, scope="spec")
    return {"ok": True, "scope": "spec", **verdict}


def plan(run_dir: str) -> dict[str, Any]:
    """Lay the scenes onto the clock and write plan.json (writes to the run)."""
    paths = run_layout.run_paths(sandbox.within(run_dir, label="run_dir"))
    if not paths.spec.is_file():
        raise FileNotFoundError(f"no spec at {paths.spec}; run colophon_init first")
    spec = load_spec(paths.spec)
    normalized, built, _ = _plan_for(spec)
    out = paths.root / "plan.json"
    write_json(built.to_dict(), out)
    return {
        "ok": True,
        "plan_path": str(out),
        "total_duration_s": round(built.total_duration_s, 3),
        "total_frames": built.total_frames,
        "fps": built.fps,
        "scenes": [
            {
                "scene_id": w.scene_id,
                "start_s": round(w.start_s, 3),
                "end_s": round(w.end_s, 3),
                "duration_frames": w.duration_frames,
            }
            for w in built.windows[:MAX_FINDINGS]
        ],
    }


def qa(run_dir: str, attempt: int | None = None) -> dict[str, Any]:
    """Run all fourteen gates on an attempt (writes qa-report.json).

    Gates that need an artifact report 'nothing to check' — a blocker — when
    the artifact is missing. Emit and render before reading those as defects.

    With no attempt named, this picks the newest attempt that was actually
    emitted from the run's current spec. An attempt left over from an older
    spec is refused rather than evaluated: its video was made by something
    else, and a report carrying today's hash would describe a video that hash
    never produced. ``attempt_provenance`` in the answer says which case it
    was — ``matches``, or ``empty`` for an attempt that has nothing in it yet.
    """
    paths = run_layout.run_paths(sandbox.within(run_dir, label="run_dir"))
    if not paths.spec.is_file():
        raise FileNotFoundError(f"no spec at {paths.spec}; run colophon_init first")
    spec = load_spec(paths.spec)
    normalized, built, _ = _plan_for(spec)

    # Choose the attempt *before* creating anything. begin_attempt() makes the
    # directory, so picking first also keeps a refused run from leaving an
    # empty attempt behind as evidence that something happened.
    expected = spec_sha256(normalized)
    number = run_manifest.evaluable_attempt(paths, expected, attempt)
    provenance = run_manifest.attempt_provenance(
        run_layout.attempt_paths(paths, number), expected
    )
    att = run_layout.begin_attempt(paths, number)

    document_path = att.project / "index.html"
    document = (
        document_path.read_text(encoding="utf-8") if document_path.is_file() else None
    )
    video = att.artifact / "launch-video.mp4"
    video_path = video if video.is_file() else None

    emit_info: dict[str, Any] = {}
    if (att.qa / "emit.json").is_file():
        emit_info = json.loads((att.qa / "emit.json").read_text(encoding="utf-8"))

    # Mirrors `colophon qa` exactly, including what it leaves out:
    # ``rendered_duration_s`` is deliberately absent. Only `colophon deliver`
    # knows a *measured* encode length, and passing a guessed one would let the
    # delivery gate fail on drift nobody measured. A QA run invoked on its own
    # compares the timeline against the plan, which is what it can prove.
    context: dict[str, Any] = {
        "spec": normalized,
        "plan": built,
        "document": document,
        "scene_fragments": emit_info.get("scene_fragments"),
        "video_path": video_path,
        "project_dir": att.project,
    }
    result = run_stages(
        qa_pipeline.full_gate_fns(),
        context,
        spec_sha256=spec_sha256(normalized),
    )
    verdict = _verdict(
        result,
        has_project=document is not None,
        has_video=video_path is not None,
        scope="full",
    )
    write_json(
        {
            "eval_fingerprint": _eval_fingerprint(),
            "assessment": taxonomy.assess(result.results).to_dict(),
            **result.to_dict(),
        },
        att.qa / "qa-report.json",
    )
    return {
        "ok": True,
        "attempt": number,
        "attempt_provenance": provenance,
        **verdict,
    }


def design(
    spec_path: str,
    out_dir: str | None = None,
    max_turns: int = harness_designer.MAX_DESIGNER_TURNS,
    render: bool = False,
    renderer: str = DEFAULT_RENDERER,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Run the bounded repair loop on a spec (writes to ``out_dir`` if given).

    Fixes mechanically what it can prove it can fix — today, non-positive scene
    durations — and stops in the ``blocked`` state for anything that needs
    judgment. It never silently ships a broken spec.
    """
    spec = load_spec(sandbox.within(spec_path, label="spec_path"))
    # `workspace` is where a render is allowed to put files, and `out_dir` is
    # where the designed spec is written. Both come from the client, so both
    # are confined the same way — a workspace is not a promise that the paths
    # inside it are trustworthy.
    safe_workspace = sandbox.within_optional(workspace, label="workspace")
    settings = harness_designer.DesignerSettings(
        max_turns=max_turns,
        default_scene_duration_s=harness_designer.DEFAULT_SCENE_DURATION_S,
    )
    driver = None
    if render:
        from .harness import orchestrator as harness_orchestrator

        driver = harness_orchestrator.make_runtime_driver(
            renderer=renderer,
            workspace=None if safe_workspace is None else str(safe_workspace),
        )
    session = harness_designer.run_design_loop(
        spec,
        settings=settings,
        driver=driver,
        workspace=None if safe_workspace is None else str(safe_workspace),
    )

    written: dict[str, str] = {}
    if out_dir:
        out = sandbox.within(out_dir, label="out_dir")
        out.mkdir(parents=True, exist_ok=True)
        save_spec(session.final_spec, out / "spec.designed.json")
        write_json(session.to_dict(), out / "design-session.json")
        written = {
            "spec": str(out / "spec.designed.json"),
            "session": str(out / "design-session.json"),
        }

    return {
        "ok": True,
        "state": session.assessment.state,
        "shippable": session.shippable,
        "aborted": session.aborted,
        "abort_reason": session.abort_reason,
        "turns_used": session.turns_used,
        "final_spec_sha256": session.to_dict()["final_spec_sha256"],
        "render_attestation": session.render_attestation,
        "blockers": [_finding(f) for f in session.assessment.blockers[:MAX_FINDINGS]],
        "turns": [
            {
                "turn": t.turn,
                "mechanical_codes": [c or "<uncoded>" for c in t.mechanical_codes],
                "judgment_codes": [c or "<uncoded>" for c in t.llm_codes],
                "llm_outcome": t.llm_outcome,
                "state_after": t.state_after,
                "note": t.note,
            }
            for t in session.turns[:MAX_FINDINGS]
        ],
        "written": written,
        "hint": (
            "the loop only fixes what it can prove is safe to fix; anything "
            "needing judgment is left blocked for the caller to resolve"
        ),
    }


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _plan_for(spec: VideoSpec):
    """Normalize, then build the timeline plan. Same order the CLI uses."""
    normalized, log = normalize(spec)
    return normalized, build_plan(normalized), log


def _eval_fingerprint() -> dict[str, Any]:
    from .qa import eval_protocol

    return eval_protocol.compute_eval_fingerprint()


# --------------------------------------------------------------------------
# Server construction
# --------------------------------------------------------------------------

#: (function, tool name, description). Kept as data so the functions above stay
#: ordinary, testable Python that never imports an MCP library.
TOOLS: tuple[tuple[Callable[..., Any], str, str], ...] = (
    (
        gates,
        "colophon_gates",
        "List colophon's fourteen QA gates, what each checks, and what artifact "
        "it needs before it can tell the truth. Call this first.",
    ),
    (
        doctor,
        "colophon_doctor",
        "Check whether this machine has the runtime colophon needs. Read-only.",
    ),
    (
        init_run,
        "colophon_init",
        "Freeze a spec JSON file into a new run directory. Writes into the run "
        "directory you name, and nowhere else.",
    ),
    (
        validate,
        "colophon_validate",
        "Run the four spec-level gates on a run. Needs no emitted project and "
        "no video, so it is the cheap check to loop on while editing a spec.",
    ),
    (
        plan,
        "colophon_plan",
        "Lay the scenes onto the clock and write plan.json into the run "
        "directory. Writes into the run directory you name, and nowhere else.",
    ),
    (
        qa,
        "colophon_qa",
        "Run all fourteen gates on an attempt. Writes qa-report.json into the "
        "run directory. Gates needing a missing artifact report 'nothing to "
        "check' and block — that is by design, not a defect.",
    ),
    (
        design,
        "colophon_design",
        "Run the bounded repair loop on a spec. Fixes only what it can prove is "
        "safe to fix, and stops blocked for anything needing judgment.",
    ),
)


def guarded(fn: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
    """Turn a raising tool into one that reports the failure instead.

    The functions above raise on a missing spec or a missing attempt, which is
    right for a library and wrong for an agent: an MCP-level error is a
    protocol event, not a readable answer. Wrapping at registration time (rather
    than decorating the definitions) keeps the functions themselves plain and
    directly testable, including their exception behaviour.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - tool boundary, same as the CLI's
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return wrapper


def _register_tool(
    server: Any, fn: Callable[..., Any], name: str, description: str
) -> None:
    """Register one tool, tolerating the two shapes of fastmcp's API.

    Across the version range ``pyproject.toml`` allows, ``add_tool`` has meant
    two different things: it used to take a function plus ``name=`` and
    ``description=`` keywords, and it now takes a ``Tool`` object built by
    ``Tool.from_function``. Both spellings are current somewhere in that range,
    so try the newer one and fall back.

    The incompatibility surfaces as a ``TypeError`` or ``ImportError`` raised
    while constructing the tool — before anything is registered — so there is
    no partial state to unwind if the first attempt fails.
    """
    tool = None
    try:
        from fastmcp.tools import Tool

        tool = Tool.from_function(fn, name=name, description=description)
    except (ImportError, TypeError):
        tool = None

    if tool is not None:
        server.add_tool(tool)
        return
    server.add_tool(fn, name=name, description=description)


def is_loopback(host: str) -> bool:
    """Whether ``host`` can only be reached from this machine.

    ``localhost`` resolves through the host's own resolver, so it is treated
    as loopback only if it actually resolves to one — a machine configured to
    resolve it elsewhere is a machine we should not be trusting.
    """
    import ipaddress
    import socket

    if host in ("localhost", ""):
        try:
            resolved = {info[4][0] for info in socket.getaddrinfo(host or "localhost", None)}
        except OSError:
            return False
        return bool(resolved) and all(
            ipaddress.ip_address(addr).is_loopback for addr in resolved
        )
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        # A name we cannot parse as an address might resolve anywhere.
        return False


def build_auth(token: str) -> Any:
    """A verifier that accepts exactly one bearer token.

    Raises if fastmcp cannot provide one. The caller must treat that as
    fatal: a server that cannot check a token must not bind remotely, and
    silently starting anyway is the vulnerability this exists to close.
    """
    from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

    return StaticTokenVerifier(
        tokens={token: {"client_id": "colophon", "scopes": []}}
    )


def build_server(token: str | None = None) -> Any:
    """Build the MCP server. Requires the optional ``mcp`` dependency."""
    try:
        from fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise SystemExit(
            "the MCP server needs the optional dependency: pip install '.[mcp]'"
        ) from exc

    auth = build_auth(token) if token else None
    server = FastMCP("colophon", instructions=INSTRUCTIONS, auth=auth)
    for fn, name, description in TOOLS:
        _register_tool(server, guarded(fn), name, description)
    return server


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    path: str = DEFAULT_PATH,
    root: str | Path | None = None,
    token: str | None = None,
) -> None:
    """Run the HTTP MCP server until interrupted.

    Configures the filesystem root before anything can be called. Every path a
    tool is handed must resolve inside it, which is what keeps a client from
    using this process to write wherever it likes. The root is printed on
    startup because a silent sandbox is a sandbox nobody can check.

    Binding anywhere other than loopback requires a token. These tools write
    files and run a renderer, so an open port is not a read-only surface —
    and without a client to check, "who called this?" has no answer. The
    default host is loopback, which is the case that needs no token at all.
    """
    import os
    import sys

    sandbox.configure(root)
    token = token or os.environ.get(TOKEN_ENV) or None

    if not is_loopback(host) and not token:
        raise SystemExit(
            f"refusing to bind {host} without a token: these tools write to "
            f"disk and run a renderer, so anyone who can reach this port can "
            f"use it. Pass --token, or set {TOKEN_ENV}, or bind to "
            f"{DEFAULT_HOST}."
        )

    try:
        server = build_server(token=token)
    except (ImportError, TypeError) as exc:
        # Fail closed. An auth provider we could not build is not a detail to
        # warn about and carry on from — the server would be open.
        raise SystemExit(
            f"could not enable token auth ({exc}); refusing to start. Use an "
            f"older fastmcp that supports StaticTokenVerifier, or bind to "
            f"{DEFAULT_HOST}."
        ) from exc

    if token:
        print(
            f"colophon mcp server on {host}:{port}{path} — root "
            f"{sandbox.root()}, token auth enabled",
            file=sys.stderr,
        )
    else:
        print(
            f"colophon mcp server on {host}:{port}{path} — root "
            f"{sandbox.root()}, loopback only, no auth",
            file=sys.stderr,
        )
    server.run(transport="streamable-http", host=host, port=port, path=path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="colophon mcp", description="Expose colophon as MCP tools over HTTP."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("serve", help="run the HTTP MCP server")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--path", default=DEFAULT_PATH)
    p.add_argument(
        "--root",
        default=None,
        help=(
            "directory every tool path is confined to. Defaults to "
            f"${sandbox.ROOT_ENV} if set, else the current directory."
        ),
    )
    p.add_argument(
        "--token",
        default=None,
        help=(
            "bearer token clients must present. Required to bind anywhere but "
            f"loopback. Defaults to ${TOKEN_ENV} if set."
        ),
    )

    args = parser.parse_args(argv)
    if args.command == "serve":
        serve(
            host=args.host,
            port=args.port,
            path=args.path,
            root=args.root,
            token=args.token,
        )
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
