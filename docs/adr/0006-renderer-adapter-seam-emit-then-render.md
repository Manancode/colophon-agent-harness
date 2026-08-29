# ADR 0006 — Renderers sit behind an emit/render adapter seam

- **Status:** Accepted
- **Date:** 2026-08-29
- **Deciders:** Colophon

## Context

The first renderer is HTML/CSS based, and a second is planned. If renderer
specifics leak upward, adding that renderer means rewriting the spec, and the
spec stops being renderer-agnostic — which defeats its whole purpose.

Generate-then-render is also the shape that other implementations of this
problem have converged on independently, which is decent evidence the seam
is in the right place.

## Decision

Every renderer implements one Protocol (`renderers/base.py:RendererAdapter`)
with three members:

- `runtime_requirements()` — what tools it needs, pinned.
- `emit(spec, plan, ctx) -> EmitResult` — spec + plan → editable project files.
- `render(project_dir, ctx) -> RenderResult` — project → MP4.

Everything upstream of `emit` deals in the spec. Everything downstream of
`render` deals in an MP4 plus reports. **The adapters are the only modules
allowed to know what HTML and CSS are.**

Concretely, the spec has no renderer keys. Advisory hints live in
`Scene.renderer_hints` and are never authoritative — a renderer that ignores
every hint must still produce a valid video.

## Consequences

- `emit` output is a real, editable artifact in the run directory
  (`attempts/NN/project/index.html`). Hand-editing it works and is inspectable;
  the next `emit` regenerates it.
- A second renderer needs no spec changes. Its composition declaration maps
  1:1 onto `Canvas` plus the plan.
- Renderer-specific traps are contained. Brand data declared in renderer code
  is the classic trap; ours reaches the renderer as CSS custom properties
  from `assets/brand.py`.
- Cost: an extra indirection, and `scene_fragments()` must be implemented per
  renderer for grounding (see ADR 0005).

## Rejected

- **One renderer, no seam.** Faster now; makes a second renderer a rewrite.
- **Per-renderer spec dialects.** Lets each renderer be optimal and destroys the
  ability to diff two runs that used different renderers.
