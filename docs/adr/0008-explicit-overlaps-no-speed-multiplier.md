# ADR 0008 — Explicit overlaps for match cuts; no global speed multiplier

- **Status:** Accepted
- **Date:** 2026-08-29
- **Deciders:** Colophon

## Context

We designed the timeline as strictly adjacent: each scene starts exactly where
the previous one ends. It is the obvious model and it is wrong.

Reading every render file in a shipped project — not its README, which describes
a different, simpler thing — showed that the shipped document overlaps at
**every** boundary: `-7, -7, -12, -6, -8` frames, each carrying a `matchCut`
transition. Overlaps are not an edge case in launch videos; they are how scenes
are joined.

The same files carried `playbackSpeed: 1.25` across the whole document. That
silently turned an advertised 22.3s into an actual 17.87s. Nobody chose 17.87s.

So: one mechanism we were missing, and one mechanism we must never add.

## Decision

1. **Overlaps are explicit and bounded.** `timeline.overlap_s` (seconds) plus
   `timeline.transition` ∈ `{cut, match_cut, fade}` and `transition_ms`.
   `build_plan` clamps the overlap so no scene can be consumed by its
   neighbour. `check_continuity` permits overlaps up to the configured maximum
   and treats any *gap* as a bug.
2. **There is no global speed field.** See ADR 0002. If a scene should move
   faster, its `duration_s` changes.

## Consequences

- Match cuts are expressible, and the overlap is a declared number in the diff
  rather than an emergent property of six independent clip timings.
- `match_cut` with `overlap_s: 0` is rejected — the transition would have
  nothing to cross-cut with.
- `timeline.policy: "explicit"` (per-scene absolute starts) is declared in the
  schema and **rejected by validation in V0**. It is the shape we expect to need
  once a human hand-tunes a timeline, and we would rather reject it than
  half-implement it.
- The Cadence example uses `overlap_s: 0.25` ≈ 7 frames at 30fps, matching the
  magnitude observed in real launch documents.

## Rejected

- **Strictly adjacent scenes.** Cannot express the transition the reference
  video actually used.
- **`playback_speed`.** Rejected outright, with the 22.3s → 17.9s discrepancy as
  the recorded reason.
