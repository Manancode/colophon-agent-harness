# ADR 0005 — Grounding is checked against emitted output, not against the spec

- **Status:** Accepted
- **Date:** 2026-08-29
- **Deciders:** Colophon

## Context

Grounding means: everything visible on screen is traceable to a claim in the
spec. The tempting place to enforce it is the spec — check that each scene
references a claim, and you are done.

That check passes while the video lies.

The spec can be perfectly well-formed and the emitted HTML can still print a
number that no claim contains, because the renderer is where claims become
strings. We call this failure `unbound_visible_number`, and it is only
detectable after emission.

## Decision

Grounding is asserted on the **emitted project**, not the spec.

`qa/stages/grounding.py` runs after `emit` and parses the actual scene
fragments. For each scene it enforces:

- `unbound_visible_number` — every number rendered on screen appears in a bound
  claim for that scene.
- `title_mismatch` / `title_missing` — the rendered `<h1>` matches the claim
  bound to that scene, byte for byte.
- `narration_clause_dropped` — every clause of the bound narration claim is
  present in the output.

This is also why treatments *split* bound claims rather than authoring copy. If
the layout only ever subdivides text that already came from a claim, an unbound
number is not merely detected — it is difficult to construct.

## Consequences

- The check is renderer-agnostic in principle but needs a fragment source per
  renderer; `scene_fragments()` is part of the adapter contract for that
  reason.
- "Forty percent" in a claim blocks `stat-hero`, because rendering `40%` would
  be a claim the source never made. Blocking is correct behaviour, and the Cadence
  `brief.md` records it as a deliberate example.

## Rejected

- **Spec-level grounding only.** Catches malformed specs, not lying videos.
- **Pixel-level visual QA as a substitute.** Reviews composition and can catch
  some of this, but it is non-deterministic and cannot prove a number is bound.
