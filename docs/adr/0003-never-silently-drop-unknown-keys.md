# ADR 0003 — Never silently drop an unknown spec key

- **Status:** Accepted
- **Date:** 2026-08-29
- **Deciders:** Colophon

## Context

This ADR exists because of one specific bug.

A permissive normaliser rebuilt each scene from a fixed set of keys:

```python
Scene(**{k: raw[k] for k in ("scene_id", "role", "duration_s", ...)})
```

When the planner later emitted `treatment`, the normalizer did not know the key,
so it did not copy it — and raised nothing. The treatment vanished. The
symptom surfaced much later, as six scenes that all rendered with the default
layout, and the investigation started from "the renderer is wrong".

The expensive part was not the bug. It was that the failure was **silent**, at a
distance from its cause, and presented as a rendering problem.

## Decision

Unknown keys are a hard error. `spec/validate.py:reject_unknown_keys()` checks
every level of the document — top, canvas, brand, timeline, asset, claim, scene
— and raises `SpecError` naming the offending key and its path.

The rule it enforces: **the schema may be small, but it is closed.** If a field
is worth an agent emitting, it is worth an explicit key in the schema. If it is
not in the schema, the run fails loudly at the boundary where the mistake was
made.

`presentation/normalize.py` follows the same principle for values: an
unrecognised treatment name raises rather than falling back to a default.

## Consequences

- Adding a field is a deliberate, reviewable schema change, not an accident.
- An agent that hallucinates a key gets an immediate, actionable error naming
  the key — which is also the ideal repair hint.
- Cost: forward compatibility is weaker. A spec written for a newer Colophon
  will not load in an older one. We accept that; version is `spec_version` and
  mismatches are reported.

## Rejected

- **Warn and continue.** This is what a permissive normaliser effectively does.
  It converts a 30-second diagnosis into a multi-hour one.
- **Store unknown keys in an `extra` bag.** Preserves data but not meaning; the
  next layer still does not know what to do with it, so the drop just moves.
