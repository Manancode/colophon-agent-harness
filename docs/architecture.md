# Architecture

## The one idea

A launch video is not a file. It is a **spec**, a **project**, a **render**, and
a **record**, and conflating those four is what makes video tooling painful.

Our starting point was a renderer document that *was* the source of truth — a
766 KB JSON blob that was then hand-edited to produce the final video. The
hand-editing worked well and is a genuinely good workflow. What made it fragile
is that the same file was simultaneously the plan, the project, the asset
store and the timeline, so no part of it could be validated, diffed or hashed
independently.

Colophon keeps the workflow and splits the file.

## The four artifacts

| Artifact | Lives at | Written by | Can a human edit it? |
|---|---|---|---|
| **Spec** | `<run>/spec.json` | the agent | Yes — this is the source of truth |
| **Project** | `<run>/attempts/NN/project/index.html` | the renderer adapter | Yes — regenerated on next emit |
| **Video** | `<run>/attempts/NN/artifact/launch-video.mp4` | the renderer | No |
| **Record** | manifests, QA reports, reviews | the harness | No |

The spec is written once at `init` and **never rewritten**. Attempts only read
it. That single rule is what makes "which spec made this video?" answerable.

## Layer boundaries

```
         ┌─────────────────────────────────────────────┐
         │  brief + brand + assets        (input)      │
         └───────────────────┬─────────────────────────┘
                             │  agent
         ┌───────────────────▼─────────────────────────┐
 spec/   │  VideoSpec  —  canonical, renderer-agnostic │
 content/│  claims + grounding                         │
 timeline/│  seconds → frames                          │
 present/ │  roles + treatments                        │
 assets/  │  brand tokens + asset registry             │
         └───────────────────┬─────────────────────────┘
                             │  emit
         ┌───────────────────▼─────────────────────────┐
 renderers/│  HTML/CSS adapter (the only renderer in V0) │
         └───────────────────┬─────────────────────────┘
                             │  render
         ┌───────────────────▼─────────────────────────┐
 qa/     │  deterministic stages                       │
 review/ │  frame extraction + human/model verdict      │
 repair/ │  spec diff + locality proof                  │
 runs/   │  attempts, hashes, recovery                  │
 runtime/│  tool discovery + pinning                    │
         └─────────────────────────────────────────────┘
```

The rule that holds this together: **the renderer adapters are the only place
allowed to know what HTML and CSS are.** Everything upstream
deals in the spec; everything downstream deals in an MP4 plus a report.

## Why each separation exists

- **content / timeline / presentation.** Content is *what is said*, timeline is
  *when*, presentation is *how it looks*. A treatment change must never move
  the clock; a timing change must never change copy. Keeping the modules apart
  makes that a structural guarantee rather than a discipline.
- **assets.** Content-addressed and local-only. A remote URL makes a render
  non-reproducible the moment the URL changes.
- **evaluation (qa + review).** QA is deterministic and machine-run; review is
  independent and can be human or model. They must not share code, or "the
  tests pass" starts to mean "the reviewer agreed with the generator".
- **runtime.** Tool discovery and pinning is separate because it is the part
  that varies between machines, and a run needs to say *which* ffmpeg rendered
  it.

## Design principles

Each of these is a lesson that cost us something. They are stated as rules
because a rule can be linted and a war story cannot.

1. **Canonical spec hashing and run binding.** Every report records the spec's
   sha256; every artifact is traceable to it.
2. **The stage contract.** Each QA stage returns PASS/FAIL plus artifacts and
   diagnostics, and no stage mutates another's inputs.
3. **A hard-reject vocabulary.** `unbound_visible_number`, `title_mismatch`,
   remote assets, inline event handlers. Naming a failure is what makes it
   enforceable rather than aspirational.
4. **The scene grammar.** Roles × treatments, each with an explicit
   precondition checked against bound claims.
5. **Grounding by construction.** Treatments split bound narration instead of
   authoring copy, so an unbound number is structurally impossible rather than
   merely detected.
6. **The canvas audit walks ancestors only.** A clip's own background must be
   the brand colour; descendants are unconstrained. That is where all visual
   variation legally lives.
7. **Motion on descendant wrappers, pushing in from an opacity floor (0.85)
   rather than fading from 0.** This is what stops blank frames at scene
   boundaries.
8. **`@font-face { src: local(...) }` for OS-bundled fonts.** The renderer
   hard-rejects a font family without a declaration; `local()` satisfies it
   without a network fetch, so determinism is preserved.
9. **Attempt / review / recovery run layout**, with a delivery report per
   attempt.
10. **Generate, then render.** Emitting a project before rendering it is what
    makes the project inspectable and QA-able before render time is spent.
11. **A flat ordered clip list is the right timeline shape.** Layers that are
    1:1 with clips buy nothing.

### Anti-patterns this architecture refuses

- **Timing constants in code.** Hardcode `TITLE_HOLD_FRAMES = 100` and change
  the fps and every one of them silently means something else. Here timing is
  data in the spec, never a constant in code.
- **Generated code committed to the repo.** We emit generated files into the
  run directory, where they are hashed with everything else and are disposable.
- **Brand colours declared in components.** A module-level `colors = { ... }`
  object is brand data living in renderer code. Ours comes from
  `assets/brand.py` and reaches the renderer as CSS custom properties.
- **Renderer props in the plan.** Zoom factors, cursor steps and sky colours
  are renderer capabilities, not content. Our spec has no renderer keys;
  advisory hints live in `renderer_hints` and are never authoritative.
- **A document-wide speed multiplier.** We have seen a `playbackSpeed: 1.25`
  silently turn an advertised 22.3s into an actual 17.9s. There is no such
  field here; speed belongs in a scene's own timing.
- **Strictly adjacent scenes.** Real launch videos overlap their scene
  boundaries by 6–12 frames with a `matchCut`. A strictly adjacent timeline
  cannot express that, so `timeline.overlap_s` exists (the example uses
  0.25s ≈ 7 frames).

## The agent runtime

`colophon/adapters/agent/bridge.py` translates a spec into a model-friendly
payload and QA failures into repair hints. It is one-way: nothing in the core
imports it, and the pipeline runs to completion with the file deleted. An agent
runtime is a caller, not a dependency.

## Not in V0

- **A second renderer.** The adapter seam exists so this needs no spec change,
  but only the HTML/CSS adapter ships in V0.
- **MetaHarness / RL.** Explicitly deferred.
- **Partial re-rendering.** V0 re-renders the whole project but still measures
  locality, so the guarantee is already instrumented when partial support
  arrives.
- **`timeline.policy: "explicit"`.** Rejected by validation in V0.
- **TTS.** Narration audio enters as a content-hashed asset; V0 does not
  synthesize it.
