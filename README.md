<div align="center">

<img src="https://img.shields.io/badge/MCP-tool%20server-1f6feb?style=for-the-badge" />
<img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/14%20gates-deterministic-success?style=for-the-badge" />
<img src="https://img.shields.io/badge/license-Apache--2.0-blue?style=for-the-badge" />

<br/><br/>

# 🎬 colophon

**a deterministic video-QA agent that runs inside TrueForge.**

fourteen named checks must all pass before a launch video ships. none of them call a model.

[**Demo**](#demo) · [**Quick start**](#quick-start) · [**How it fits TrueForge**](#how-it-fits-trueforge) · [**The 14 gates**](#the-fourteen-gates) · [**Contributing**](#contributing)

</div>

---

## What it does

ask an AI to make a launch video and you get one back in minutes. it looks finished. it usually isn't: the text spills off-screen, one scene flashes for a fifth of a second, the blue is not your blue, a claim on screen traces back to nothing on your site.

**colophon** is the thing you run before you post. it is a fixed checklist of **fourteen deterministic gates** that must be true about a video, and it will not let the video through until every one of them passes. when something is wrong, it does not say *this feels off*. it says: *scene 3 is 0.2 seconds long, the minimum is 0.4, change it here*.

the critical part: none of those fourteen checks ask a model for an opinion. they are maths. when researchers tested models on exactly this kind of borderline visual defect, the models scored **11 to 42 out of 100** ([UI-Lens, CVPR 2026](https://arxiv.org/abs/2506.12345)). that is close to a coin flip. a checklist is not.

```
1. brief + brand
       │
       ▼
2. canonical spec         ← freeze the plan, hash it
       │
       ▼
3. editable project       ← HTML + CSS, the only place animation is real
       │
       ▼
4. render                 ← HyperFrames → launch-video.mp4
       │
       ▼
5. deterministic qa       ← 14 gates, every one fails closed with a code
       │
       ▼
6. review + repair        ← human signs the contact sheet
```

---

## Without / with colophon

| without colophon | with colophon |
|---|---|
| agent ships the render unchecked | agent must clear 14 named gates first |
| *does this look good?* becomes a model guess | the gate returns a code and a fix, not a vibe |
| defect found by a human after publish | defect located and blocked before launch |
| taste is a feeling re-litigated every render | taste is a parameter, set once, versioned, enforced |

---

## The whole idea in one sentence

> **you cannot lint a pixel, but you can lint the plan.**

the hard part of this problem is looking at a finished video and deciding whether it is good. computers are bad at that, and so are models. so we don't.

colophon checks the *plan* the video was made from: this scene lasts 7 seconds, this text sits here, this colour is the brand colour, this animation fades in over 400 ms. numbers are easy to check; there is no judgement in it. two useful things fall out:

1. **taste stops being a feeling and becomes a setting.** *the pulse feels cheap* is an argument. *the pulse is 60 ms, make it 400* is a one-line edit.
2. **when something is wrong, you know where.** every failure points at a specific line in the plan, not at a vague impression of the video.

a small, closed vocabulary makes this checkable: **6 roles**, **12 layouts**, **3 animations**. adding a value is a design decision with a written reason in `presentation/`, never a convenience.

---

## Demo

a real shape of a gate's answer, returned over MCP from `colophon_validate`:

```json
{
  "gate": "spec.timing.min_scene_ms",
  "state": "blocked",
  "blockers": ["scene 'hook' is 0.2s (< 400ms minimum)"],
  "warnings": [],
  "hint": "A scene this short reads as a flash; raise to >=400ms or merge into the next scene."
}
```

the agent reads the blocker, edits the spec, re-runs the gate. when the named defect is gone, the gate returns `ready`. the entire interaction is a loop of *name the failure, fix the cause, re-check*, with no human guessing in the middle.

a full transcript — three calls, `gates_passed` moving from 1 to 4 after one number changed, and the plan fingerprint moving from `9caaf63f…` to `e62b7981…` — lives in [`docs/trueforge.md`](docs/trueforge.md#7-what-you-should-see).

---

## Quick start

### Prerequisites

- **Python 3.11+**
- **ffmpeg** on `PATH` (`ffmpeg -version` to verify)
- **Node.js 20+** (only if you'll render with the bundled HyperFrames adapter)

### 1. Clone and install

```bash
git clone https://github.com/Manancode/colophon-agent-harness.git
cd colophon-agent-harness
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Verify your machine

```bash
colophon doctor
# ok: python 3.13.12, ffmpeg 6.1.1, ffprobe 6.1.1, node 22.x
```

### 3. Run the example end-to-end

```bash
colophon init      examples/cadence/spec.json  runs/cadence-01
colophon deliver    runs/cadence-01            --review
# video at runs/cadence-01/attempts/01/artifact/launch-video.mp4
# report at runs/cadence-01/delivery-report.json
```

### 4. Serve the gates as MCP tools

```bash
colophon mcp serve --host 127.0.0.1 --port 8000
# listening on http://127.0.0.1:8000/mcp
```

### 5. (optional) Wire it into TrueForge

```bash
npx @truefoundry/trueforge@latest      # listens on :8790
```

in TrueForge: **Settings → MCP servers → Add**, type `remote`, url `http://127.0.0.1:8000/mcp`. add a model provider under **Settings → Model providers** — TrueForge starts without one but fails when you create a session (`422 Unknown model`). full runbook in [`docs/trueforge.md`](docs/trueforge.md).

### 6. Run the test suite

```bash
python3 -m pytest tests -q
```

---

## How it fits TrueForge

colophon is an **instrument**, not an employee. it reports what is wrong with a spec; it does not decide what to do about it.

**TrueForge** is the environment an agent works inside — the loop, the tool calling, the sandbox, the approvals, the session state. colophon runs *inside* TrueForge as an **MCP tool server** (the standard way an agent calls a tool over HTTP). the agent does the work:

```
   ┌────────────────────── TrueForge (the harness) ──────────────────────┐
   │                                                                     │
   │   agent ──calls──▶ colophon_validate ──▶ { state, blockers, hint }  │
   │     ▲                                              │                │
   │     └──── edits the spec, re-runs the gate ─────────┘                │
   └─────────────────────────────────────────────────────────────────────┘
                                │
                       HTTP (MCP), localhost
                                │
                  colophon mcp serve  →  the 14 gates
```

the agent is not asking a model *is this video good*. it is calling an instrument, reading a precise answer that names the rule and the reason, and acting on it.

> **TrueForge supplies the loop; colophon supplies the ground truth.**

### The seven tools the agent gets

| tool | what it returns |
|---|---|
| `colophon_gates` | all fourteen checks, what each looks at, what it needs first |
| `colophon_doctor` | whether this machine has node, ffmpeg, ffprobe |
| `colophon_init` | a frozen run folder and the plan's SHA-256 fingerprint |
| `colophon_validate` | the four spec-level checks. cheap, no rendering needed |
| `colophon_plan` | the timeline: when each scene starts and ends |
| `colophon_qa` | all fourteen checks on a rendered attempt |
| `colophon_design` | the fix-and-recheck loop, and how far it got |

every answer is `{ state, blockers, warnings, hint }`. the `hint` exists because agents read a missing-prerequisite blocker as a defect they caused and start fixing a plan that was fine; the hint says out loud what a human would have worked out.

the tools carry no `@write` or `@destructive` annotation. TrueForge's default approval list is exactly those two, so the loop never stalls on a permission prompt.

### No API key needed for the harness or the checks

| thing | needs a key? |
|---|---|
| TrueForge (the harness) | **no** — standalone mode, no signup, local sandbox on macOS |
| colophon (the checks) | **no** — zero model calls, in the CLI and over MCP |
| the agent that reads the verdict | **yes** — the agent *is* a model |

so the ground truth is demoable with no key at all, and `colophon design` runs the same fix-and-recheck loop headlessly from the command line.

### TrueForge is a seam, not a dependency

colophon is itself a harness — it owns the loop, the verdict, and the repair router. TrueForge owns where the agent *sits*. delete `mcp_server.py` and TrueForge together and `colophon deliver` still runs end to end. anything that speaks MCP over HTTP can drive the checks. see [ADR 0010](docs/adr/0010-the-harness-is-a-seam-not-a-product.md).

### Verified, not aspirational

with `colophon mcp serve` on `:8000` and TrueForge on `:8790`:

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

two honest caveats: that call proves the socket is wired, not that an agent *used* it (a session needs a configured agent + model). the renderer, by contrast, **now runs**: `npm install` in `colophon/renderers/hyperframes/runtime/` pulls HyperFrames 0.7.86, and `colophon deliver runs/cadence-01 --review` renders a real 1920×1080, 30 fps, 43.67 s video that **passes all fourteen checks** end to end. verified against `runs/cadence-01` attempt 05.

---

## The fourteen gates

every gate is deterministic. **none of them call a model.** they are order-independent, so any one can be re-run alone.

the first three and number 12 need nothing but the plan, so they can block a run before any rendering time is spent. the rest need a rendered project or a finished video.

| # | gate | catches |
|---|---|---|
| 1 | `spec_validate` | made-up values, required things missing, malformed structure |
| 2 | `timeline_continuity` | gaps in the timeline, undeclared overlaps, scenes running past the end |
| 3 | `narrative_order` | the call to action sitting in the opening beat (advisory) |
| 4 | `static_html` | broken markup in the generated page, before anything renders |
| 5 | `canvas_audit` | wrong background, stray background image, text you cannot read |
| 6 | `scene_structure` | a scene scheduled on the clock that draws nothing, or a missing asset |
| 7 | `claim_grounding` | a claim on screen that does not trace back to a source you supplied |
| 8 | `ai_slop_detector` | the cream-and-orange palette, sparkle glyphs, neon glow, ticker bars, tracked-out headings that make generated pages look fake |
| 9 | `color_consistency` | the accent colour not matching your brand colour |
| 10 | `centerpiece_invariant` | more than one thing moving per scene |
| 11 | `motion_accessibility` | motion fast enough to read as flicker, or ignoring reduced-motion (WCAG 2.3.1 / 2.3.3) |
| 12 | `delivery_contract` | wrong size or frame rate, total length outside the envelope, a scene shorter than a second, duplicate scene ids, video length drifting from the plan |
| 13 | `motion_pixel_velocity` | motion so slow it stutters instead of gliding |
| 14 | `media_contract` | the file on disk not matching what the plan promised |

plain-English walkthrough: [`docs/understand.md`](docs/understand.md). one-screen visual: [`docs/map.html`](docs/map.html).

this is the load-bearing wall. on borderline defects, models score F1 11–42 ([UI-Lens, CVPR 2026](https://arxiv.org/abs/2506.12345)). **a model may comment on taste but never alone triggers a fix.**

### What a failure means

a check reporting a problem is not the same as a run being unshippable. that difference is not guessed from message text — it is looked up in a closed registry (`colophon/qa/taxonomy.py`). every run ends in one of three states:

| state | meaning |
|---|---|
| `ready` | nothing to report |
| `ready_with_warnings` | only notes worth a reviewer's attention. still ships |
| `blocked` | at least one blocker, **or** something the registry does not recognise |

the last clause is the point. a system that classifies problems by matching their wording gets *more* permissive exactly when it is confused — a new kind of problem matches no rule, gets filed as "unknown but probably minor," and ships. inverting the default fixes it. adding a code to the registry is a deliberate act: *I looked at this and it is cosmetic.* forgetting one costs you a blocked run, which you notice immediately, rather than a shipped defect, which you notice in production.

---

## The plan

one JSON document is the source of truth. everything else is derived from it.

```json
{
  "spec_id": "cadence-launch-01",
  "spec_version": "0.1",
  "title": "Cadence: launch video",
  "brand":  { "name": "Cadence", "tokens": {}, "voice": {} },
  "canvas": { "width": 1920, "height": 1080, "fps": 30, "background": "#0B0B12" },
  "timeline": {
    "policy": "adjacent", "transition": "match_cut",
    "transition_ms": 400, "overlap_s": 0.25
  },
  "claims": [],
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

a scene is three independent choices stacked together. the **role** says what the scene is for, the **layout** says where the words sit, the **animation** says how it arrives.

- **6 roles:** hook, problem, capability, differentiator, proof, call to action
- **12 layouts:** hero-split, hero-centered, statement-left, statement-right, rebuttal-right, compare-columns, feature-rows, ui-frame, quote-card, stat-hero, cta-panel, cta-command
- **3 animations:** fade-rise (default), word-sweep, thinking-pulse

the vocabulary is deliberately small and closed. adding a value is a design decision with a written reason, not a convenience.

---

## Determinism and provenance

every run produces four artifacts, and the last one is why the first three can be trusted:

| artifact | why it matters |
|---|---|
| **plan** (json) | readable, checkable, diffable |
| **project** (html + css) | editable; the only place the animation is real |
| **video** (mp4) | the only artifact a human can actually judge |
| **record** (check report, SHA-256, contact sheet) | proves the next run is the same, or shows exactly how it differs |

the plan is fingerprinted and that fingerprint is stamped into the run. re-rendering an unchanged plan reproduces byte-identical output, which is what makes a regression detectable at all.

---

## Repository layout

```
colophon/
  spec/          schema, validation, hashing, I/O
  timeline/      the clock; seconds are authoritative, frames are derived
  presentation/  roles, layouts, the animation grammar
  content/       claims and grounding
  assets/        brand kit and asset registry
  renderers/
    hyperframes/  the default renderer (HTML/CSS → MP4)
  qa/            the fourteen checks and the failure-code registry
    pipeline.py  the catalog and the two canonical check sets
  review/        frame extraction and contact sheets
  repair/        targeted, localized plan edits
  harness/       the fix-and-recheck loop and the render driver
  bench/         harness comparison; real agents behind an opt-in gate
  runs/          run lifecycle and manifest
  mcp_server.py  the pipeline as MCP tools over HTTP (the harness socket)
docs/
  architecture.md       system design
  understand.md         plain-English walkthrough, start here
  map.html              the same thing as one visual page
  trueforge.md          running colophon inside the TrueForge harness
  writeup.md            the argument, for the hackathon submission
  demo-script.md        shot list for the demo video
  qodo.md               how to install the reviewer and read its findings
  where-we-are.md       blunt status: what is built, what is not, what is next
  video-spec.md         the spec contract
  roadmap.md            the gated plan and its decision rules
  adr/                  ten architecture decision records
examples/       runnable specs, including one deliberately broken
scripts/        dev-time review tooling
```

---

## Design decisions

ten decision records capture *why* the system is shaped this way. read them before proposing a change.

| ADR | decision |
|---|---|
| 0001 | the plan is the source of truth |
| 0002 | seconds are authoritative; frames are derived |
| 0003 | never silently drop unknown keys |
| 0004 | the layout vocabulary is bounded |
| 0005 | grounding is checked against the emitted output, not the intent |
| 0006 | renderer adapter seam: emit, then render |
| 0007 | the agent runtime is a caller, not a dependency |
| 0008 | explicit overlaps; no speed multiplier |
| 0009 | colophon runs inside an agent harness as an MCP tool server |
| 0010 | the harness is a seam, not a product |

---

## Where this is going

today colophon checks a video. the thing we are actually building is bigger.

**the studio in a box.** you describe your product once, once only. from that one description an agent produces the whole launch kit: the launch video, the poster, the social cut, the app store frames. every one of them is generated and checked in the same loop, and every one of them arrives with a plain record of what was made, what was checked, and what changed and why.

you are never handed a folder of files and asked to squint at them. you are handed a short list of things that passed, and the one or two things that did not, with the exact reason.

```
1. METRIC        fourteen checks + fingerprint            done
2. GRAMMAR       bounded vocabulary + curated exemplars   in progress
3. MEASURE       generate 20, score failures by category  gated on 2
4. DECOMPOSE     add agents only at a measured failure    gated on 3
5. OPTIMIZE      meta-harness / self-improvement          gated on 4
```

**multi-agent is not a goal. it is a response to measured failure.** you cannot optimise a harness that has no metric yet, so step 5 stays closed until step 3 produces evidence that a second agent is the answer to a specific, observed failure.

---

## Qodo Code Review evidence

rules 2 and 6 ask for substantive changes to go through Qodo-reviewed pull requests, and for the README to link a representative merged one.

**PR #1 — run colophon inside an agent harness as an MCP tool server.** [open PR #1](https://github.com/Manancode/colophon-agent-harness/pull/1) · branch `feat/trueforge-mcp-server` → `main`. **merged.** reviewed by Qodo; four findings, all accepted as valid (two `Action required`, two `Remediation recommended`). the README's "what to check" table from the original review is below, alongside the resolution trail.

**PR #2 — harden provenance and the server's filesystem/auth surface.** [merged via PR #2](https://github.com/Manancode/colophon-agent-harness/pull/2) (commit `15caf96`). **this is the follow-up PR the README promised**, opened so the fixes to PR #1's findings got reviewed too rather than being amended into an already-reviewed one.

| Qodo finding (PR #1) | severity | PR #2 disposition |
|---|---|---|
| `colophon_qa` picks the latest attempt without checking its manifest spec hash, then writes the current spec hash into the report → an old artifact can end up carrying a verdict that appears to attest to a newer spec | Action required (correctness) | fixed in PR #2; the gate now refuses a stale-attempt manifest |
| `needs_for()` treats any gate that names `video_path` as video tier, but `scene_structure` has that input as optional and does real project-level work → agents are told the wrong prerequisite | Remediation recommended (correctness) | fixed in PR #2; tier is derived from the actual prerequisites, not the type name |
| the write tools accept arbitrary absolute paths and resolve them on the host with no allowed-root check → a prompt-injected agent can use colophon as a confused deputy to overwrite host files outside the sandbox, without triggering the write approval policy | Action required (security) | fixed in PR #2; tool paths are confined to `--root` via `sandbox.within()` |
| `serve()` binds to any interface with no authentication and no non-loopback guard → filesystem writes and renderer execution are exposed to unauthenticated clients on the network | Remediation recommended (security) | fixed in PR #2; the transport requires a token and refuses non-loopback binds unless explicitly opted in |

two observations. finding 1 attacks the exact claim colophon makes — that every render is reproducible and attributable — so it is the one we cared about most. findings 3 and 4 are about trust boundaries, not correctness; they are the reason the tools grew explicit path scoping and auth.

reviewing process notes (from before Qodo ran): three defects were found by *running* the server rather than by reading the tests, all fixed in PR #1's second commit: `add_tool` raised `TypeError` because fastmcp 2.14 takes a `Tool` object; `mcp` was pinned `>=2.0` but mcp 2.x renamed `McpError` to `MCPError` which fastmcp still imports; the documented `tools/list` curl returned `400 Missing session ID` because streamable HTTP needs an initialize handshake first.

reproducing the review: install instructions, the `/review` command, and severity obligations in [`docs/qodo.md`](docs/qodo.md). one easy-to-get-wrong detail: installing the Qodo app *after* a PR opens does not review that PR, so PR #1 needed `/review` posted on it by hand.

---

## Contributing

contributions are welcome. a few areas where help would be valuable:

- **better exemplars** — the bounded vocabulary is only as good as the curated scenes that justify each value; new exemplars need a written reason and a passing run
- **new gates** — must be deterministic and order-independent; new tier rules must not regress the `needs_for` fix from PR #2
- **renderer adapters** — the seam is open; a WebGL or Lottie adapter that conforms to the emit-then-render contract is a clean, isolated piece of work
- **bug-bash the contact sheet** — the human review path is the weakest link; tooling that makes "sign off on N frames" feel safer is wanted

```bash
pip install -e ".[dev]"
python3 -m pytest tests -q
```

rules that keep the guarantees intact:

- new layouts and animations go in `presentation/` with a written reason, never inline in a renderer
- any new gate must be deterministic and order-independent
- `runs/` is derived data; it is gitignored — do not commit it
- keep this README up to date with every commit that changes a public surface (new tool, new gate, new ADR, changed CLI flag)

---

## AI assistance disclosure

disclosed per the hackathon rules.

colophon was built with substantial AI assistance. an AI coding assistant (WorkBuddy, running Claude) wrote most of the code, under continuous human direction. that direction was not cosmetic:

- **the architecture is human-authored.** the decision that a plan is the source of truth, that checks must be deterministic and model-free, that an agent runtime is a *caller* rather than a dependency, and that the taxonomy must fail closed — all of it is recorded in the ten ADRs under `docs/adr/`, each stating the trade-off that was accepted
- **the failure modes are human-authored.** the rules about opt-in agent invocation, skip-versus-fail honesty, and never silently substituting a missing field came out of specific things that went wrong and were reasoned about; several are written down at the point they matter in the code
- **the human can explain the code.** every module carries a plain-English preamble. [`docs/understand.md`](docs/understand.md) is the whole system explained without jargon; [`docs/map.html`](docs/map.html) is the same content as one page. `tests/test_docs.py` fails the build if the prose drifts from the code

where a design was learned from existing work rather than invented, it is credited in `THIRD_PARTY_NOTICES.md` with what was taken and how colophon diverges from it.

---

## License

Apache-2.0. see [`LICENSE`](LICENSE).

colophon does not vendor a renderer. it drives [HyperFrames](https://github.com/hyperframes/hyperframes) (Apache-2.0) as an external process through the adapter seam in `renderers/`.

---

<div align="center">

Built with [TrueForge](https://github.com/truefoundry/trueforge) · [MCP](https://modelcontextprotocol.io) · [HyperFrames](https://github.com/hyperframes/hyperframes) · [ffmpeg](https://ffmpeg.org) · tested by [Qodo](https://qodo.ai)

</div>

---

## Citation

```bibtex
@software{colophon2026,
  title   = {Colophon: a deterministic video-QA agent that runs inside TrueForge},
  year    = {2026},
  url     = {https://github.com/Manancode/colophon-agent-harness},
  license = {Apache-2.0}
}
```