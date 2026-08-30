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

## Prior art (validated by research, 2026-08-30)

The closed-grammar instinct is not novel, and naming the lineage makes the
decision defensible to a jury instead of merely plausible:

- **VBench** (vchitect.github.io/VBench-project; CVPR 2024 Highlight). "Video
  quality" decomposes into ~16 *disentangled, machine-scored* dimensions
  (subject/background consistency, color, spatial relationship, temporal
  flickering, motion smoothness, aesthetic quality, …). This is the empirical
  backbone for the determinism/taste split: the dimensions VBench scores are
  exactly the ones colophon checks deterministically, and the ones it leaves
  to a human ("aesthetic quality", "dynamic degree") are the ones colophon
  leaves to the reviewer.
- **Motion Grammar** (blakecrosley.com, "Motion Grammar: When Animation
  Earns Its Frames"). "Motion is information or it is noise." A *closed*
  vocabulary of four duration bands (~100ms press, 150–200ms hover/fade,
  250–300ms expand, 300–400ms page/modal) plus two easing rules. colophon's
  `treatments` are his "jobs" and its `motions` are his "bands"; the
  `prefers-reduced-motion` gate and the 400ms cap on `thinking-pulse` are
  straight applications of his rules. His line — "the deletion test outranks
  the taste test" — is the project's load-bearing principle.
- **The AI Aesthetic** (HN thread news.ycombinator.com/item?id=49117099;
  Jim Nielsen, blog.jim-nielsen.com/2026/ai-aesthetic). LLMs trained for
  consistency converge on a generic mean; the tells are catalogued
  (beige/cream, orange accent, serif, sparkle ✨, shimmering "thinking" text,
  tiny icons). colophon's `ai_slop_detector` gate turns that catalogue into a
  check.
- **Launch-video structure** (dmakproductions.com, "Product Launch Video").
  Practitioners converge on a six-beat arc — hook, problem, reveal,
  demo/proof, benefit, CTA — and warn that "showing capabilities it can't
  deliver can end a launch in court." That is an independent confirmation of
  both colophon's six-role model and its claim-grounding layer.
- **ViMAX** (github.com/hkuds/vimax). A *multi-agent, stochastic* video
  pipeline (Director / Screenwriter / Producer / Generator). It is the
  contrast case: where ViMAX throws agents at taste, colophon encodes taste
  as a deterministic layer. This is the white-space the project occupies.
- **Minimum-jerk motor control** (Hogan 1984; Flash & Hogan 1985; Todorov &
  Jordan, *J Neurophysiol* 1998; reviewed in
  pmc.ncbi.nlm.nih.gov/articles/PMC6758108). The deepest grounding the motion
  layer has, and it is scientific rather than stylistic. The CNS plans
  reaching movements by minimising the integral of squared jerk, and that
  same optimisation reproduces the two-thirds power law — the paper reports
  "a unification of the two-thirds power law and smoothness hypotheses." The
  bell-shaped velocity profile that falls out of it *is* ease-in-out. So
  ease-in-out is not a convention to be defended by taste; it is the
  trajectory a human motor system would have chosen, which is why a flat
  linear ramp reads as mechanical. The per-keyframe easing on
  `thinking-pulse` (anticipation → strike → settle) is an application.
- **The AI aesthetic, mainstreamed** (The New Yorker, Kyle Chayka, "The
  A.I.-Design Aesthetic That's Taking Over the Internet"). The trade press
  reached the same catalogue as HN and independently named four tells that
  are expressible in CSS: beige/cream grounds with rusty orange accents,
  "tracked out" subheads, ticker-style text bars, and rounded rectangles with
  a neon glow. That working designers named these in a general-audience
  publication is what justifies encoding them as gates rather than opinions.
- **AIGVE survey** (Safavigerdini et al., "Generative AI Video Evaluation:
  Survey of Metrics, Benchmarks, and Trustworthiness", CVPRW 2026). The
  field's own self-critique: VBench and EvalCrafter "often fall short in
  assessing dynamic scenarios, primarily due to their reliance on
  subject-centric, static prompts and frame-level metrics", and they
  "prioritize aesthetic fidelity over cinematic camera motion and temporal
  causality." It names the current phase as a shift toward "trustworthy,
  agentic evaluation frameworks" — precisely the niche colophon fills.
- **NVIDIA Video Storyboarding** (Atzmon et al., arXiv:2412.07750). Self-attention
  query features "encode both motion and identity", producing a "hard-to-avoid
  trade-off between preserving character identity and making videos dynamic."
  colophon does not solve that trade-off; it *sidesteps* it, because a
  template-driven renderer has perfect identity consistency by construction.
  Determinism is usually sold as a limitation. Here it is the fix.
- **Constrained decoding is not a guarantee** (Geng et al.,
  arXiv:2501.10868; aidancooper.co.uk/constrained-decoding). Constrained
  decoding guarantees *schema compliance*, but there is "poor understanding
  of the effectiveness of the methods in practice", and independent
  measurements found that reordering schema fields or stripping token
  whitespace dropped field accuracy from roughly 50% into the 29–35% range.
  This is why colophon validates the artifact deterministically *after*
  generation rather than trusting the generator's format compliance.
- **WCAG 2.3.1 / 2.3.3** (w3.org/WAI/WCAG22) — three-flashes-or-below-threshold
  and animation-from-interactions. The `motion_accessibility` gate enforces a
  100ms duration floor and requires a `prefers-reduced-motion` block, treating
  the accessibility floor as a hard gate rather than a nicety.
