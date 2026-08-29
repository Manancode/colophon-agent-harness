# ADR 0007 — The agent runtime is a caller, not a dependency

- **Status:** Accepted
- **Date:** 2026-08-29
- **Deciders:** Colophon

## Context

An agent runtime is how we want to drive this pipeline. But the pipeline has to
keep working when the agent layer is swapped, absent, or being debugged — a
pipeline you cannot run by hand is a pipeline you cannot trust.

## Decision

The dependency is strictly one-way.

`colophon/adapters/agent/bridge.py` translates:

- a spec into a model-friendly payload (`spec_to_payload`,
  `spec_to_prompt_context`),
- QA failures into repair hints (`qa_problems_to_patch_hints`).

**Nothing in `colophon/` imports it.** The enforcement is structural rather
than a convention: deleting `adapters/` entirely must leave the harness able to
run `init → plan → validate → emit → render → qa → review → repair → deliver`
from the CLI with no change in behaviour.

## Consequences

- The CLI is the reference driver. Any agent integration is a second client of
  the same code path, so its output is comparable to a manual run.
- Repair hints are derived from the same `SpecError` / problem objects the CLI
  prints, so an agent and a human see the same diagnosis.
- Cost: the bridge can drift from the core, since nothing imports it. Mitigated
  by keeping it thin and translation-only.

## Rejected

- **Agent-shaped core types.** Convenient now, and makes the pipeline unusable
  without that agent.
- **A plugin interface with runtime registration.** Over-engineering for a
  single known caller; a one-way translation module is enough.
