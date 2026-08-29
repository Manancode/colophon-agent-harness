# ADR 0001 — The canonical spec is the source of truth

- **Status:** Accepted
- **Date:** 2026-08-29
- **Deciders:** Colophon

## Context

Our starting point was a renderer document that *was* the plan: a 766 KB JSON
blob that was simultaneously the project, the asset store and the timeline.
It was then hand-edited to produce the final video, and that worked well —
the hand-editing is a good workflow and we want to keep it.

What made it fragile was not the editing. It was that one file played four
roles at once, so no part of it could be validated, diffed, or hashed
independently. Answering "which plan produced this video?" required keeping
copies of the file and comparing them by hand.

## Decision

There is exactly one source of truth: `spec.json`, written once at `init` and
**never rewritten**.

Everything else is derived:

| Artifact | Derived from | Human-editable |
|---|---|---|
| `spec.json` | the brief, via the agent | **Yes** — this is the point |
| `attempts/NN/project/index.html` | spec, via `emit` | Yes, but regenerated on next emit |
| `attempts/NN/artifact/launch-video.mp4` | project, via `render` | No |
| manifests, QA reports, reviews | everything above | No |

Attempts only ever *read* the spec. A repair edits the spec and opens a **new**
attempt; it never rewrites the spec that an earlier attempt already recorded a
hash of.

## Consequences

- Every report, manifest and review records `spec_sha256`. "Which spec made
  this video?" is a hash lookup, not archaeology.
- The spec is written with `canonical_bytes()` (sorted keys, no incidental
  whitespace, UTF-8 unescaped) so the hash is stable across machines and
  Python versions.
- Because the spec is human-editable and authoritative, hand-editing it is a
  first-class workflow, but now with a validator and a hash behind it.
- Cost: a change requires a new attempt rather than an in-place edit. That cost
  is the price of being able to answer provenance questions.

## Rejected

- **Letting the emitted project be authoritative.** Tempting because it is what
  the renderer reads, but it is renderer-specific, so the same spec could not
  target more than one renderer.
- **Mutable spec with per-attempt snapshots.** Equivalent provenance with more
  moving parts and a confusing question about which copy is "current".
