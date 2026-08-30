# Colophon — agent harness for spec-first video generation

**Spec-first video generation with machine-checkable taste.**

A closed motion grammar, fourteen deterministic QA gates, and a reproducible
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
                                  deterministic QA   ← 14 gates, no model calls
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
| A scene is 0.2 s long. Text overflows. The colour isn't the brand colour. A claim isn't supported by its source. | a computer | **solved** — 14 gates |
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
| `qa` | run the fourteen deterministic gates |
| `review` | extract frames and build a contact sheet |
| `record-review` | validate an independent review and merge the verdicts |
| `repair` | apply targeted spec repairs |
| `design` | run the repair loop on a spec (`--render` also drives the renderer) |
| `deliver` | run the whole pipeline end to end |
| `resume` | show the resumable attempt |
| `bench` | compare harnesses; `--agents` runs real codex/claude |
| `mcp` | serve the pipeline as MCP tools over HTTP, for an agent harness |

---

## How it uses TrueForge

Colophon is an instrument, not an employee. It reports what is wrong with a
video spec; it does not decide what to do about it. **TrueForge** is the
environment an agent works inside — the loop, the tool calling, the sandbox,
the approvals, the session state — so it is where an agent belongs when the job
is "read the report and act on it".

The integration is not a wrapper. Colophon runs **inside** TrueForge as an MCP
tool server, and the agent does the work:

```
   ┌──────────────────────── TrueForge (the harness) ────────────────────────┐
   │                                                                         │
   │   agent ──calls──> colophon_validate ──> { state, blockers, hint }      │
   │     ▲                                              │                    │
   │     └──── edits the spec, re-runs the gate ─────────┘                   │
   └─────────────────────────────────────────────────────────────────────────┘
                                   │
                         HTTP (MCP), localhost
                                   │
                    colophon mcp serve  →  the 14 gates
```

The agent is not asking a model "is this video good?" — on boundary defects
that is close to a coin flip (UI-Lens, CVPR 2026: F1 11–42). It is calling a
deterministic instrument, reading a precise answer naming the gate and the
failure code, and acting on it. **The harness supplies the loop; colophon
supplies the ground truth.**

### Setting it up

```bash
# 1. colophon, with the optional MCP transport
pip install -e '.[dev,mcp]'

# 2. serve the tools (leave running)
colophon mcp serve --host 127.0.0.1 --port 8000

# 3. start the harness (local/standalone mode; no signup, no setup wizard)
npx @truefoundry/trueforge@latest      # listens on :8790
```

Then in TrueForge: **Settings → MCP servers → Add**, type `remote`, URL
`http://127.0.0.1:8000/mcp`. Add a model provider under **Settings → Model
providers** — TrueForge starts fine without one but fails at session creation
(`422 Unknown model`).

Full runbook, including what the transcript should look like and the gotchas:
[docs/trueforge.md](docs/trueforge.md).

### The seven tools the agent gets

| Tool | Returns |
|---|---|
| `colophon_gates` | All 14 gates, what each checks, and what artifact it needs first |
| `colophon_doctor` | Whether this machine has node / ffmpeg / ffprobe |
| `colophon_init` | A frozen run directory and the spec's SHA-256 |
| `colophon_validate` | The 4 spec-level gates — cheap, no artifacts needed |
| `colophon_plan` | The timeline: when every scene starts and ends |
| `colophon_qa` | All 14 gates on an attempt |
| `colophon_design` | The bounded repair loop, and how far it got |

Every answer is `{ state, blockers, warnings, hint }`. The `hint` exists
because of a specific way agents get this wrong: before an artifact exists,
several gates report *"nothing to check"*, and colophon counts that as a
blocker — correctly, since failing closed is the point. An agent that doesn't
know this reads the blocker as a defect it caused and starts "fixing" a spec
that was fine. The hint says out loud what a human would have inferred.

None of the tools carry `@write` / `@destructive` annotations. TrueForge's
default approval list is exactly those two, and unannotated tools are exempt —
so the loop does not stall on permission prompts.

### No API key is needed for the harness or the gates

| Thing | Needs a key? |
|---|---|
| TrueForge (the harness) | **No** — standalone mode, no signup, local sandbox on macOS |
| Colophon (the gates) | **No** — zero model calls, in the CLI and over MCP |
| The agent that reads the verdict | **Yes** — the agent *is* a model |

TrueForge starts and serves its UI with no provider configured; it fails only
when you create a session (`422 Unknown model "<fqn>"`). Colophon's fourteen
gates make no model calls at all. So the ground truth is demoable with no key
whatsoever, and `colophon design` runs the same repair loop headlessly from the
CLI — no agent, no key, no harness.

### TrueForge is a seam, not a dependency

Colophon is itself a harness: it owns the loop, the verdict and the repair
router. TrueForge owns where the agent *sits* while it works. Delete
`mcp_server.py` and TrueForge together and `colophon deliver` still runs end to
end. Anything that speaks MCP over HTTP can drive the gates; TrueForge is
today's choice, not a lock-in — see
[ADR 0010](docs/adr/0010-the-harness-is-a-seam-not-a-product.md).

The longer version of the argument, including what is honestly still missing,
is in [docs/writeup.md](docs/writeup.md).

### Verified

The wiring above is not aspirational — it was run. With `colophon mcp serve` on
`:8000` and TrueForge on `:8790`:

```bash
$ curl -s http://localhost:8790/api/v1/mcp-servers/colophon/tools
colophon_gates      List colophon's fourteen QA gates, what each checks, and
                    what artifact it needs before it can run.
colophon_doctor     Check whether this machine has the runtime colophon needs.
colophon_init       Freeze a spec JSON file into a new run directory.
colophon_validate   Run the four spec-level gates on a run.
colophon_plan       Lay the scenes onto the clock and write plan.json.
colophon_qa         Run all fourteen gates on an attempt.
colophon_design     Run the bounded repair loop on a spec.
```

And a real three-call loop against `examples/broken-duration.json`, ending in
`gates_passed` moving 1 → 4 with one number changed, and the spec hash moving
`9caaf63f…` → `e62b7981…`. The full transcript is in
[docs/trueforge.md](docs/trueforge.md#7-what-you-should-see).

Two caveats stated plainly: that call proves the socket is wired, not that an
agent used it (a session needs a configured agent and model). The renderer, by
contrast, **now runs**: `npm install` in
`colophon/renderers/hyperframes/runtime/` pulls HyperFrames 0.7.86, and
`colophon deliver runs/cadence-01 --review` renders a real 1920×1080, 30 fps,
43.67 s video that **all 14 gates pass** end to end — verified against
`runs/cadence-01` attempt 05, not assumed.

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

## The fourteen gates

Every gate is deterministic. **No stage calls a model.** Stages are
order-independent, so any single one can be re-run alone.

Listed in the order `colophon qa` runs them. Rows 1–3 and 12 need nothing but
the spec, so they can gate a run before any render time is spent; the rest need
an emitted project or a rendered video.

| # | Gate | Catches | Needs |
|---|---|---|---|
| 1 | `spec_validate` | unknown enum values, missing required fields, malformed structure | spec |
| 2 | `timeline_continuity` | gaps, undeclared overlaps, scenes off the clock | spec |
| 3 | `narrative_order` | a `cta` in the opening beat, roles out of sequence (advisory) | spec |
| 4 | `static_html` | lint on the emitted markup before anything is rendered | project |
| 5 | `canvas_audit` | wrong background, stray `background-image`, invisible text | project |
| 6 | `scene_structure` | a scene scheduled on the clock that draws nothing, or a missing asset | project |
| 7 | `claim_grounding` | every on-screen claim traces back to a supplied source | project |
| 8 | `ai_slop_detector` | cream+orange palette, sparkle glyph in copy, neon glow / ticker bar / tracked-out heading in CSS | project |
| 9 | `color_consistency` | emitted `--accent` matches the brand token (no off-brand hue) | project |
| 10 | `centerpiece_invariant` | exactly one motion target per scene; `thinking-pulse` requires one | project |
| 11 | `motion_accessibility` | missing `prefers-reduced-motion`, or motion fast enough to read as flicker (WCAG 2.3.1 / 2.3.3) | project |
| 12 | `delivery_contract` | canvas or fps off contract, total duration outside the envelope, scene count out of range, sub-second scene, duplicate `scene_id`, rendered length drifting from the timeline | spec, enhanced by render |
| 13 | `motion_pixel_velocity` | motion slower than ~1px/frame stutters (no sub-pixel render); also word-sweep stagger below 2 frames | project |
| 14 | `media_contract` | the file on disk matches what the spec promised: resolution, fps, duration | video |

For a plain-English walkthrough of all of this, see
[docs/understand.md](docs/understand.md), or open
[docs/map.html](docs/map.html) for the one-screen visual version.

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
  qa/            the fourteen gates and the failure-code registry
    pipeline.py    the gate catalog and the two canonical gate sets
  review/        frame extraction and contact sheets
  repair/        targeted, localized spec edits
  harness/       the repair loop and the render driver
  bench/         harness comparison; real agents behind an opt-in gate
  runs/          run lifecycle and manifest
  mcp_server.py  the pipeline as MCP tools over HTTP (the harness socket)
docs/
  architecture.md        system design
  understand.md          plain-English walkthrough — start here
  map.html               the same thing as one visual page
  trueforge.md           running colophon inside the TrueForge harness
  writeup.md             the argument, for the hackathon submission
  demo-script.md         shot list for the demo video
  qodo.md                how to install the reviewer and read its findings
  where-we-are.md        blunt status: what is built, what is not, what is next
  video-spec.md          the spec contract
  roadmap.md             the gated plan and its decision rules
  adr/                   ten architecture decision records
examples/        runnable specs, including one deliberately broken
scripts/         dev-time review tooling
```

---

## Design decisions

Ten ADRs record *why* the system is shaped this way. Read them before
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
| 0009 | Colophon runs inside an agent harness as an MCP tool server |
| 0010 | The harness is a seam, not a product |

---

## Where this is going

The architecture is deliberately gated. Each step unlocks the next, and the
decision rule for every outcome is committed in advance — see
`docs/roadmap.md`.

```
1. METRIC        14 deterministic gates + fingerprint       done
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

## Demo video

> **TODO — the author records this.** I cannot generate video. ~3 minutes. Full
> shot list, timings and narration in [docs/demo-script.md](docs/demo-script.md),
> including a no-key fallback if you would rather not configure a model.

The shape of it, so the harness work is visible rather than asserted:

| Time | What is on screen |
|---|---|
| 0:00–0:20 | The problem: an agent that generates a video and ships it unchecked. |
| 0:20–0:50 | `colophon mcp serve` + `npx @truefoundry/trueforge@latest`, side by side. |
| 0:50–2:10 | **The loop.** Live in the TrueForge chat: `colophon_validate` returns `blocked` with a named gate and code → the agent edits the spec → re-runs → `ready`. Do this twice, once for a spec-level fix and once for something it cannot fix. |
| 2:10–2:40 | `colophon_qa` on a rendered attempt: all 14 gates, showing the ones that need a real artifact. |
| 2:40–3:00 | Why this isn't a wrapper: the gates hold the veto; the model never does. |

---

## Qodo Code Review Evidence

Rules 2 and 6 ask for substantive changes to go through Qodo-reviewed pull
requests, and for the README to link a representative merged one.

**Representative PR:** <https://github.com/Manancode/colophon-agent-harness/pull/1>

**Branch:** `feat/trueforge-mcp-server` → `main`

**Status:** open, not yet reviewed. Qodo is not installed on this repository at
the time of writing, so review is pending rather than done. It is listed here
anyway because the honest state is more useful than a green tick.

**What is in it, and what a reviewer should look at:**

| Area | What to check |
|---|---|
| `qa/pipeline.py` | The gate classification is *derived* from each gate's signature, not hand-listed. Is the derivation sound? |
| `mcp_server.py` | Every tool is a plain function behind a registration table. Every exception at the tool boundary is caught and returned as `{"ok": false, "error": ...}` rather than raised. Deliberate — see the ADR — but it is a real trade. |
| `mcp_server.py` | `_register_tool` tries two shapes of fastmcp's `add_tool` and falls back. Is that the right amount of defensiveness, or is it hiding a pin we should make strict? |
| `tests/test_mcp_server.py` | 21 tests that call the tool functions directly and never import an MCP library. Good for coverage, and it is precisely why a broken *registration* path passed 445 tests. |

**The honest history:**

* The 25 commits before this work were **direct pushes to `main`**. They cannot
  be retro-fitted with a review trail — a Qodo comment on a commit that never
  went through a PR is not evidence of review. They are disclosed as unreviewed.
* Everything from here on goes through a PR. This is the first one in the
  repository's history.

**What review has already changed, before Qodo ran:**

Three defects were found by *running* the server rather than by reading the
tests, all fixed in the second commit of this PR:

1. `add_tool` raised `TypeError` — fastmcp 2.14 takes a `Tool` object, not a
   function with `name=`/`description=` keywords. Nothing caught it because
   nothing built a server.
2. `mcp` was pinned `>=2.0`; mcp 2.x renamed `McpError` to `MCPError`, which
   fastmcp still imports, so the extra installed but would not import. Pinned
   `>=1.10,<2`.
3. Every documented `tools/list` curl returned `400 Missing session ID`,
   because streamable HTTP needs an initialize handshake first. Replaced with
   `scripts/mcp_call.py`.

Every valid **High** finding will be fixed or dismissed with a written reason.
**Medium** and **Low** are an engineering call, and where one is dismissed the
reason goes in the table above rather than being quietly dropped.

**Reproducing the review:** install instructions, the `/review` command, and the
severity obligations are in [docs/qodo.md](docs/qodo.md). One thing that is easy
to get wrong — installing the app *after* a PR opens does not review that PR, so
PR #1 needs `/review` posted on it by hand.

---

## AI assistance disclosure

Disclosed per the hackathon rules.

Colophon was built with substantial AI assistance — an AI coding assistant
(WorkBuddy, running Claude) wrote most of the code, under continuous human
direction. That direction was not cosmetic:

* **The architecture is human-authored.** The decision that a spec is the source
  of truth, that gates must be deterministic and model-free, that an agent
  runtime is a *caller* rather than a dependency, and that the taxonomy must
  fail closed — all of it is recorded in the ten ADRs under `docs/adr/`, and
  each one states the trade-off that was accepted.
* **The failure modes are human-authored.** The rules about opt-in agent
  invocation, SKIP-versus-FAIL honesty, and never silently substituting a
  missing field came out of specific things that went wrong and were reasoned
  about. Several are written down at the point they matter in the code.
* **The human can explain the code.** Every module carries a plain-English
  preamble — [docs/understand.md](docs/understand.md) is the whole system
  explained without jargon, and [docs/map.html](docs/map.html) is the same
  content as one page. `tests/test_docs.py` fails the build if the prose drifts
  from the code.

Where a design was learned from existing work rather than invented, it is
credited in `THIRD_PARTY_NOTICES.md` with what was taken and how colophon
diverges from it.

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
