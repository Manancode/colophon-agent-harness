# ADR 0002 — Seconds are authoritative, frames are derived

- **Status:** Accepted
- **Date:** 2026-08-29
- **Deciders:** Colophon

## Context

Video is measured in frames; people plan in seconds. Every tool that lets both
into the same document ends up with two sources of truth for one quantity, and
they drift.

A document that carries frame counts alongside a `playbackSpeed: 1.25`
multiplier applied across the whole document ends up with three numbers that
each look reasonable alone. The result: the advertised duration is 22.3s and
the actual render is 17.87s. Nobody decided that. It fell out of the
arithmetic.

## Decision

Scene durations are authored **in seconds** (`Scene.duration_s`). Frames exist
only as a derived quantity, computed by a single `FrameClock` at plan time.

- There is exactly one rounding step per scene, and starts are **cumulative**,
  so rounding error never compounds down the timeline.
- There is **no** document-wide speed, scale, or time-warp field. Changing pace
  means changing a scene's own `duration_s`, which is visible in the diff.

## Consequences

- The advertised duration is the rendered duration, to within one frame per
  scene. QA can assert that, and does (`media_contract`).
- A retiming change shows up in `repair` as a changed scene duration, not as a
  mysterious global shift.
- Cost: an author who thinks in frames must convert. `FrameClock.timecode()`
  exists so reports can show both without letting frames become input.

## Rejected

- **Authoring in frames.** Matches the renderer but not the brief, and makes
  any fps change a content edit.
- **`playback_speed` as a spec field.** Directly rejected because of the
  22.3s → 17.9s discrepancy above. A multiplier that silently rescales
  everything is worse than no multiplier.
