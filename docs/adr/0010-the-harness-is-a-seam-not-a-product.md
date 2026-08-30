# ADR 0010 — The harness is a seam, not a product

- **Status:** Accepted
- **Date:** 2026-08-30
- **Deciders:** Colophon

## Context

ADR 0009 established that colophon runs *inside* an agent harness as an MCP
tool server, and named TrueForge as the harness used today. That ADR does not
say what happens if the harness changes, and the wording invited a
misreading: that colophon had adopted TrueForge as part of its stack.

It has not. Colophon is itself a harness. It owns the thing a harness is for:
a bounded loop, a verdict that names its own evidence, and a repair router
that picks the cheapest fix. What colophon does not own is the *runtime* — the
place an agent sits while it reads that verdict and acts on it. Those are two
different jobs, and only one of them belongs to us.

Concretely, the split is:

| Concern | Owner |
|---|---|
| What "wrong" means, and how precisely it can be located | colophon (the gates) |
| Whether a run ships | colophon (the taxonomy) |
| What to try next, and when to stop | colophon (the repair loop) |
| Where the agent sits while it works | a runtime — TrueForge, today |
| What the agent is allowed to touch | a runtime — sandbox + approvals |
| Which model thinks | a runtime, and the user's key |

TrueForge is valuable as the second column, not the first. It supplies the
loop, the tool calling, the sandbox, the approvals and the session state; it
does not supply the ground truth, and it must not, because its model is a
coin flip on exactly the defects colophon exists to catch.

There is also a practical constraint that makes this decision rather than
philosophy: TrueForge's MCP client only supports `remote` (HTTP) servers, and
its skills are git-backed only. Both are properties of one vendor's runtime.
Colophon must not be shaped by either.

## Decision

1. **Colophon never depends on a runtime.** Delete `mcp_server.py`, delete
   TrueForge, and `colophon deliver` still runs end to end. This is ADR 0007
   applied to the transport.
2. **The seam is MCP over HTTP, and it is the whole seam.** Anything that
   speaks MCP over HTTP can drive colophon: TrueForge, an IDE agent, a Python
   script, a CI job. No runtime-specific code lives in colophon.
3. **The seven tools are the complete contract.** A runtime needs nothing else
   — no colophon-internal imports, no shared process, no filesystem
   convention beyond "the run directory the caller names".
4. **Colophon's own loop is runtime-agnostic by construction.**
   `colophon/harness/designer.py` runs identically from the CLI, from a test,
   and from an agent. Calling it through a harness adds an agent; it does not
   change what the loop does.
5. **The model is somebody else's key and somebody else's choice.** Colophon
   makes no model calls in any gate, and the MCP tools make none either. A
   runtime that needs a model needs a key; that is a property of the runtime,
   not of colophon.
6. **Where a runtime imposes a constraint, colophon absorbs it at the edge,
   not in the core.** TrueForge's HTTP-only MCP is why `mcp_server.py` serves
   HTTP rather than stdio. That is one file, and it is the correct place for
   the accommodation.

## Consequences

- TrueForge is swappable, and swapping it is a configuration change, not a
  refactor. Point a different client at `http://127.0.0.1:8000/mcp`.
- Colophon can be driven by *more than one* runtime at once, including none.
  The CLI path is a first-class driver and is the one the test suite exercises.
- The demo is not what proves the design. A transcript of an agent calling
  `colophon_validate` shows the seam working; it does not make the seam
  necessary. The necessity argument is this ADR plus the gates themselves.
- Cost: MCP is a lowest common denominator. Everything the tools return is
  JSON, so richer affordances (streaming progress, typed errors) are
  unavailable. Accepted — a verdict that is a dict of strings is already more
  than a gate needs to say.
- Cost: two ways in (CLI and MCP) can drift. Mitigated by `qa/pipeline.py`
  owning both canonical gate sets, and by `tests/test_mcp_server.py` calling
  the tool functions directly rather than through a client.

## Rejected

- **Treating TrueForge as the product and colophon as a plugin.** Inverts the
  ownership. The gates are the asset; a runtime is a place to run them.
- **A colophon-specific runtime adapter layer.** Every abstraction between
  "tool call" and "gate function" is a place for the two to disagree. The MCP
  contract is already the abstraction.
- **Letting a runtime's skill format drive colophon's docs.** TrueForge never
  parses `SKILL.md` frontmatter and only accepts git-hosted skills, so
  `skills/colophon/SKILL.md` is published for humans and for git installation.
  Colophon's operating instructions do not live only there.
- **Bundling a model or a key.** Fourteen gates make zero model calls. Adding
  one to make a demo smoother would remove the property the demo is
  demonstrating.
