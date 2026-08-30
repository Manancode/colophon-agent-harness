# ADR 0009 — Colophon runs inside an agent harness as an MCP tool server

- **Status:** Accepted
- **Date:** 2026-08-30
- **Deciders:** Colophon

## Context

Colophon is an instrument, not an employee. It reports what is wrong with a
video spec; it does not decide what to do about it. Something has to close that
loop — read the verdict, change something, look again.

The obvious candidate is a model. It is the wrong one. Visual QA by vision
model scores F1 11–42 on boundary defects (UI-Lens, CVPR 2026), which is close
to a coin flip on precisely the subtle failures that matter most: a scene that
stutters, an accent that is one hue off, a number on screen with no source.
Asking "is this video good?" and taking the answer is not checking anything.

What is missing is not judgment. It is the **loop**: take an action, observe a
precise result, act again. That is what an *agent harness* is — the environment
an agent works inside, supplying the loop, the tool calling, the sandbox, the
approvals and the session state. (This is the same sense in which a coding
assistant runs inside its own harness: the harness is the runtime, and the model
is only one part of it.) The harness is therefore where an agent belongs when
the job is "read the report and act on it".

ADR 0007 already established that an agent runtime is a *caller*, not a
dependency. This ADR extends that: the pipeline must keep running to completion
with the harness deleted, and this socket must be additive.

## Decision

Colophon runs **inside** the harness as an MCP tool server — it does not call
out to one.

1. `colophon/mcp_server.py` exposes seven tools over streamable HTTP
   (`colophon mcp serve`, default `127.0.0.1:8000/mcp`).
2. **The tools are plain functions.** Registration is a data table (`TOOLS`),
   not decorators on closures, so the functions are unit-testable without an
   MCP library installed and the whole suite still runs without it.
3. The MCP transport is an **optional extra** (`pip install '.[mcp]'`). The
   core stays pure standard library — nothing a caller depends on may change
   the bytes the renderer emits.
4. **No tool carries `@write` or `@destructive` annotations.** TrueForge's
   default approval list is exactly those two, and unannotated tools are
   exempt, so the loop does not stall on permission prompts. Tools that do
   write say so in their description and write only inside the run directory
   the caller names.
5. **Every verdict has the same shape**: `{ state, blockers, warnings, hint }`.
   The `hint` is mandatory, not decorative (see Consequences).
6. **The agent never gets a veto.** Deterministic gates decide; a model may
   comment on taste and cannot alone trigger a repair.

## Consequences

- The core is unaffected. Delete `mcp_server.py` and `colophon deliver` still
  runs end to end — the socket is additive, satisfying ADR 0007.
- The harness is swappable. Anything that speaks MCP over HTTP can drive
  colophon; TrueForge is today's choice, not a lock-in.
- **The `hint` field is load-bearing.** Before an artifact exists, several gates
  report "nothing to check", and the taxonomy counts that as a blocker — which
  is correct, because failing closed is the whole point. An agent reading only
  the blocker list concludes it broke something and starts "fixing" a spec that
  was fine. The hint states out loud what a human would have inferred. This is
  not defensive documentation; it is a discovered failure mode with a fix.
- Cost: two entry points (CLI and MCP) can drift apart. Mitigated by both
  calling the same pipeline functions, and by `qa/pipeline.py` owning the two
  canonical gate sets — with the classification of each gate *derived* from its
  own signature rather than hand-listed, so a gate that grows a `video_path`
  parameter becomes a video-tier gate with no edit anywhere.

## Rejected

- **stdio MCP transport.** TrueForge's MCP client only supports `remote`
  (HTTP) servers — its server type enum has no stdio variant, so there is no
  `command` to spawn. The transport choice here is dictated entirely by that
  constraint; nothing about the tools themselves cares.
- **Colophon calling the harness.** Inverts the relationship: the pipeline
  would depend on a runtime, violating ADR 0007, and the loop would live in the
  wrong place.
- **Letting the model decide readiness.** A coin flip on boundary defects, and
  it moves the veto from a gate that can be audited to a weight that cannot.
- **Annotating the writing tools `@write`.** Truthful, and it turns every
  design-loop turn into a permission prompt. The tools are constrained to the
  run directory the caller names; the description carries the warning instead.
