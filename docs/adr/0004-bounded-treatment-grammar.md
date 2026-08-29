# ADR 0004 — A bounded scene grammar: six roles, two treatments each

- **Status:** Accepted
- **Date:** 2026-08-29
- **Deciders:** Colophon

## Context

An unbounded design space is not a feature. Given "make it look good", a
generator produces either timid sameness or unreviewable novelty, and there is
no vocabulary to say which.

We tested this directly. An early version applied one layout six times; the
video was coherent and completely forgettable. The next version gave each
scene a treatment drawn from a fixed set matched to its narrative job, and
the same copy read as an argument rather than a list.

The improvement did not come from a better renderer. It came from constraining
the choice.

## Decision

Presentation is a closed grammar, not an open field.

- **Six roles:** `hook`, `problem`, `capability`, `differentiator`, `proof`,
  `cta`. These are narrative jobs, not visual styles.
- **Two treatments per role** (twelve total), each with an explicit
  precondition checked against the scene's *bound claims*, not against prose:
  `always`, `has_number`, `has_contrast`, `has_multiple_clauses`,
  `has_audience`.

`stat-hero` requires a scene whose claims actually contain digits. Without them
it is refused, not degraded. Verified: `stat-hero` is blocked on the Cadence
example precisely because the claim says "forty percent" rather than "40%".

## Consequences

- The agent's decision is a small, reviewable choice of twelve options, and a
  reviewer can disagree with it in one sentence.
- Preconditions make a whole class of fabrication structurally unreachable:
  you cannot render a statistic that is not in the bound claims.
- Adding a treatment is a deliberate act with a declared precondition, so the
  grammar's growth is reviewable.

## Rejected

- **Free-form styling per scene.** Maximum expressiveness, zero reviewability,
  and it re-opens the door to unbound content.
- **One treatment per role.** Too coarse; the single-layout version showed it.
- **Treatment chosen by the renderer.** The renderer must not make content
  decisions; it is the only layer that knows about HTML, and that knowledge
  should not confer authority over meaning.
