# Colophon — agent harness for spec-first video generation

**Spec-first video generation with machine-checkable taste.**

A closed motion grammar, thirteen deterministic QA gates, and a reproducible
fingerprint for every render — so that what a viewer *feels* is the only thing
left to argue about.

<https://github.com/Manancode/colophon-agent-harness>

```
brief + brand + assets  →  agent  →  canonical spec   ← the source of truth
                                          ↓
                                   editable project   ← HTML + CSS, diffable
                                          ↓
                                       render         ← HyperFrames → MP4
                                          ↓
                                  deterministic QA   ← 13 gates, no model calls
                                          ↓
                                independent review   ← contact sheet for a human
                                          ↓
                                  localized repair   ← edit the spec, not the video
                                          ↓
                                   launch video
```

---

## Why this exists

An agent can write a video plan. Nothing in the stack can tell you whether the
plan will *look good*. That is the whole problem, and it splits cleanly in two:

| Kind of wrong | Caught by | Status |
|---|---|---|
| A scene is 0.2 s long. Text overflows. The colour isn't the brand colour. A claim isn't supported by its source. | a computer | **solved** — 7 gates |
| The movement feels cheap. | a human | **the only unsolved part** |

Colophon's bet is that the second kind becomes tractable if you stop letting
the agent author from nothing and instead give it a **closed vocabulary** to
choose from. Two consequences follow, and they are the entire design:

1. **You cannot lint a pixel, but you can lint a spec.** A motion is a number
   (`400ms`, `60ms` stagger, scale `1.05`), so taste becomes a parameter you can
   set, version, and enforce — not a feeling you re-litigate every render.
2. **A verdict can be located instead of interpreted.** "The pulse feels cheap"
   maps onto one of three dials — vocabulary, parameters, or precondition — and
   one edit makes it true for every future video.

> **Our job is not to read the corpus. It is to smelt it into enums.**
> A blog post is read once; a schema enum is applied a million times.

---

## Quick start

Requires Python 3.11+ and a working `ffmpeg` on `PATH`.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python3 -m colophon.cli doctor     # verify the runtime resolves
python3 -m colophon.cli init examples/cadence/spec.json runs/cadence-01
python3 -m colophon.cli deliver runs/cadence-01 --review
```

The video lands at `runs/<run>/attempts/01/artifact/launch-video.mp4`, with a
`delivery-report.json` beside it recording the spec hash, every QA stage, and
the resolved runtime.

The full command surface:

| Command | What it does |
|---|---|
| `doctor` | resolve and report the render runtime |
| `init` | freeze a spec into a new run directory |
| `plan` | lay scenes onto the clock |
| `validate` | validate spec and timeline |
| `emit` | spec → editable HTML/CSS project |
| `render` | project → MP4 |
| `qa` | run the thirteen deterministic gates |
| `review` | extract frames and build a contact sheet |
| `repair` | apply targeted spec repairs |
| `deliver` | run the whole pipeline end to end |
| `resume` | show the resumable attempt |

---

## The spec

One JSON document is the source of truth. Everything else is derived from it.

```json
{
  "spec_id": "cadence-launch-01",
  "spec_version": "0.1",
  "title": "Cadence — launch video",
  "brand":  { "name": "Cadence", "tokens": { }, "voice": { } },
  "canvas": { "width": 1920, "height": 1080, "fps": 30, "background": "#0B0B12" },
  "timeline": {
    "policy": "adjacent", "transition": "match_cut",
    "transition_ms": 400, "overlap_s": 0.25
  },
  "claims": [ ],
  "scenes": [
    {
      "scene_id": "scene_hook",
      "role": "hook",
      "treatment": "hero-split",
      "duration_s": 7.0,
      "title_claim_id": "c-hook-title",
      "narration_claim_id": "c-hook-narration",
      "asset_ids": []
    }
  ]
}
```

**A scene composes orthogonal choices** — the *role* says what the scene is
for, the *treatment* says where the copy sits, and the *motion* says how it
arrives.

**6 roles** — `hook`, `problem`, `capability`, `differentiator`, `proof`, `cta`

**12 treatments** — `hero-split`, `hero-centered`, `statement-left`,
`statement-right`, `rebuttal-right`, `compare-columns`, `feature-rows`,
`ui-frame`, `quote-card`, `stat-hero`, `cta-panel`, `cta-command`

**3 motions** — `fade-rise` (baseline), `word-sweep`, `thinking-pulse`

The grammar is deliberately small and closed. Adding a value is a design
decision with a rationale, not a convenience.

---

## The thirteen gates

Every gate is deterministic. **No stage calls a model.** Stages are
order-independent, so any single one can be re-run alone.

| # | Gate | Catches |
|---|---|---|
| 1 | `spec_validate` | unknown enum values, missing required fields, malformed structure |
| 2 | `timeline_continuity` | gaps, undeclared overlaps, scenes off the clock |
| 3 | `narrative_order` | a `cta` in the opening beat, roles out of sequence |
| 4 | `static_html` | lint on the emitted markup before anything is rendered |
| 5 | `canvas_audit` | wrong background, stray `background-image`, invisible text |
| 6 | `media_contract` | the file on disk matches what the spec promised |
| 7 | `claim_grounding` | every on-screen claim traces back to a supplied source |
| 8 | `ai_slop_detector` | cream+orange palette, sparkle glyph in copy, neon glow / ticker bar / tracked-out heading in CSS |
| 9 | `color_consistency` | emitted `--accent` matches the brand token (no off-brand hue) |
| 10 | `centerpiece_invariant` | exactly one motion target per scene; `thinking-pulse` requires one |
| 11 | `motion_accessibility` | missing `prefers-reduced-motion`, or motion fast enough to read as flicker (WCAG 2.3.1 / 2.3.3) |
| 12 | `motion_pixel_velocity` | motion slower than ~1px/frame stutters (no sub-pixel render); also word-sweep stagger below 2 frames |
| 13 | `delivery_contract` | canvas or fps off contract, total duration outside the envelope, scene count out of range, sub-second scene, duplicate `scene_id`, rendered length drifting from authored |

This is the load-bearing wall. Visual QA by vision model is close to a coin
flip on boundary defects (UI-Lens, CVPR 2026: F1 11–42), so a model may
comment on taste but **never alone triggers a repair**.

---

## What a failure means

A gate reporting a problem is not the same as a run being unshippable, and
the difference is not inferred from the message text — it is looked up in a
closed registry (`colophon/qa/taxonomy.py`). Every run ends in one of three
states:

| State | Meaning |
| --- | --- |
| `ready` | Nothing to report. |
| `ready_with_warnings` | Only diagnostics: worth a reviewer's attention, still ships. |
| `blocked` | At least one blocker, **or** something the registry does not recognise. |

The last clause is the point. A system that classifies problems by matching
their text gets *more* permissive exactly when it is confused: a new kind of
problem matches no rule, is filed as "unknown but presumably minor", and
ships. Inverting the default fixes it. An unrecognised problem is not
evidence that a thing is safe — it is evidence that we do not know what it
is — so it blocks. Adding a code to the registry is a deliberate act that
says "I looked at this and it is cosmetic"; forgetting one costs you a
blocked run, which you notice immediately, rather than a shipped defect,
which you notice in production.

Coverage is therefore allowed to be partial. Gates opt into emitting codes;
until one does, its problems fall back to the severity registered for that
stage. `spec_validate` names all of its failures; the rest are being taught.

---

## Determinism and provenance

Every run produces four artifacts, and the last is why the first three are
trustworthy:

| Artifact | Property |
|---|---|
| **Spec** — JSON | readable, lintable, diffable |
| **Project** — HTML/CSS | editable; the only place motion is real |
| **Video** — MP4 | the only artifact a human can judge |
| **Record** — QA report + SHA-256 + contact sheet | proves the next run is the same, or exactly how it differs |

The spec is hashed and the hash is stamped into the run. Re-rendering an
unchanged spec reproduces byte-identical output, which is what makes a
regression detectable at all.

---

## Repository layout

```
colophon/
  spec/          schema, validation, hashing, I/O
  timeline/      the clock; seconds are authoritative, frames are derived
  presentation/  roles, treatments, the motion grammar
  content/       claims and grounding
  assets/        brand kit and asset registry
  renderers/
    hyperframes/ the default renderer (HTML/CSS → MP4)
  qa/            the thirteen gates
  review/        frame extraction and contact sheets
  repair/        targeted, localized spec edits
  runs/          run lifecycle and manifest
docs/
  architecture.md        system design
  video-spec.md          the spec contract
  roadmap.md             the gated plan and its decision rules
  adr/                   eight architecture decision records
examples/        six runnable specs
scripts/         dev-time review tooling
```

---

## Design decisions

Eight ADRs record *why* the system is shaped this way. Read them before
proposing a change.

| ADR | Decision |
|---|---|
| 0001 | The canonical spec is the source of truth |
| 0002 | Seconds are authoritative; frames are derived |
| 0003 | Never silently drop unknown keys |
| 0004 | The treatment grammar is bounded |
| 0005 | Grounding is checked against emitted output, not intent |
| 0006 | Renderer adapter seam: emit, then render |
| 0007 | The agent runtime is a caller, not a dependency |
| 0008 | Explicit overlaps; no speed multiplier |

---

## Where this is going

The architecture is deliberately gated. Each step unlocks the next, and the
decision rule for every outcome is committed in advance — see
`docs/roadmap.md`.

```
1. METRIC        7 deterministic gates + fingerprint        done
2. GRAMMAR       bounded vocabulary + curated exemplars     in progress
3. MEASURE       generate 20, score failures by category    gated on 2
4. DECOMPOSE     add agents only at a measured failure      gated on 3
5. OPTIMIZE      meta-harness / self-improvement            gated on 4
```

**Multi-agent is not a goal. It is a response to measured failure.** You cannot
optimise a harness that has no metric yet, so step 5 stays closed until step 3
produces evidence that a second agent is the answer to a specific, observed
failure.

---

## Contributing

```bash
pip install -e ".[dev]"
python3 -m pytest tests -q
```

The core package is **pure standard library** — nothing you depend on can
change the bytes the renderer emits. Pillow is required only by `scripts/`.

Rules that keep the guarantees intact:

- New treatments and motions go in `presentation/` with a rationale, never
  inline in a renderer.
- Any new QA gate must be deterministic and order-independent.
- `runs/` is derived data. It is gitignored; do not commit it.

---

## License

Apache-2.0. See [LICENSE](LICENSE).

Colophon does not vendor a renderer. It drives
[HyperFrames](https://github.com/hyperframes/hyperframes) (Apache-2.0) as an
external process through the adapter seam in `renderers/`.

---

## Citation

```bibtex
@software{colophon2026,
  title   = {Colophon: spec-first video generation with machine-checkable taste},
  year    = {2026},
  url     = {https://github.com/Manancode/colophon-agent-harness},
  license = {Apache-2.0}
}
```
