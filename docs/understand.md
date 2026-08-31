# How colophon works, in plain English

This document assumes you can read code but would rather not have to. It
explains what the system does, why it is shaped this way, and what to run when.
Nothing here is a metaphor you have to decode later — where a technical term is
unavoidable, it is explained the first time it appears and listed again in the
[glossary](#glossary).

If you want the engineer's version instead, read
[architecture.md](architecture.md). For the same content as a single visual
page you can keep open, open [map.html](map.html).

---

## The 60-second version

Colophon turns a **written description of a video** into a **video**, and then
**argues with itself** about whether the result is any good.

The arguing part is the point. Most video generators hand you a file and a
smile. Colophon instead runs the output through **14 checks**, each of which is
a plain deterministic rule — not an opinion, not a model's guess — and reports
exactly which ones failed and why.

A useful way to hold it in your head:

> A spec is a **recipe**. The renderer is a **kitchen**. The gates are a
> **health inspector** who does not care how hard you tried.

The inspector is deliberately harsher than a human would be, because the whole
system's value is that it catches things you would otherwise notice on Twitter.

---

## The journey of one video

Four distinct things get made, and keeping them apart is the central design
decision.

```
  brief + brand + assets
            │
            ▼
   ┌────────────────┐
   │  SPEC          │  A small JSON file. The recipe. Hand-editable.
   │  spec.json     │  Written once. Never rewritten by a later step.
   └────────┬───────┘
            │  emit
            ▼
   ┌────────────────┐
   │  PROJECT       │  A folder with index.html + CSS. Inspectable,
   │  attempt/NN/   │  diffable, and disposable — regenerated on next emit.
   └────────┬───────┘
            │  render
            ▼
   ┌────────────────┐
   │  VIDEO         │  The MP4. Never edited by hand.
   │  launch.mp4    │
   └────────┬───────┘
            │  qa
            ▼
   ┌────────────────┐
   │  RECORD        │  Manifests, QA reports, hashes, review verdicts.
   │  qa/, manifest │  The proof of what happened.
   └────────────────┘
```

**Why bother splitting them?** Because when one file is simultaneously the
plan, the project, the asset store and the timeline, you cannot validate,
diff or hash any part of it independently. That is exactly the situation this
project was extracted from, and it is why "which spec made this video?" is
answerable here with a single command instead of an archaeology session.

The spec is written once at `init` and **never rewritten**. Attempts only ever
read it. That one rule is what makes every artifact traceable.

---

## The 14 gates

These are the health inspector. **No gate calls an AI model.** Every one is a
rule you could check by hand, which is why they can be trusted to block a
release.

They split into two groups, and the split matters:

**4 gates work on paper.** They only need the spec. You can run them before
spending a second of render time.

| # | Gate | What it catches, plainly |
|---|---|---|
| 1 | `spec_validate` | Unknown values, missing required fields, malformed structure. "Your recipe mentions an ingredient we don't stock." |
| 2 | `timeline_continuity` | Gaps between scenes, overlaps nobody declared, scenes scheduled off the end of the clock. |
| 3 | `narrative_order` | Structurally odd running order — a call-to-action in the opening beat, say. **Advisory only:** it comments, it does not block. |
| 4 | `delivery_contract` | The finished thing isn't actually a deliverable video: wrong canvas or frame rate, wrong total length, a scene shorter than a second, duplicate scene IDs. |

**10 gates need a real artifact.** They read the emitted HTML or the encoded
MP4.

| # | Gate | What it catches, plainly |
|---|---|---|
| 5 | `static_html` | Lint on the emitted markup: duplicate attributes, inline JavaScript event handlers, remote asset links, unsafe embedded content, fonts declared without a local source. |
| 6 | `canvas_audit` | The composition root and every clip must carry the brand background colour, and text must not be invisible against it. |
| 7 | `scene_structure` | Something is scheduled on the clock but draws nothing — a blank scene, a missing asset. |
| 8 | `claim_grounding` | Every number and claim on screen traces back to a source you supplied. Nothing is invented. |
| 9 | `ai_slop_detector` | The generic-AI look: cream-and-orange palette, sparkle glyphs in the copy, neon glow / ticker bar / tracked-out headings in the CSS. |
| 10 | `color_consistency` | The emitted accent colour is the brand accent, not some nearby hue someone eyeballed. |
| 11 | `centerpiece_invariant` | Exactly one motion focal point per scene. Two competing animations in one scene read as noise. |
| 12 | `motion_accessibility` | No opt-out for people who ask their OS to reduce motion, or motion fast enough to read as flicker (WCAG 2.3.1 / 2.3.3). |
| 13 | `motion_pixel_velocity` | Motion slower than about 1 pixel per frame visibly stutters, because screens cannot render half a pixel. Also catches word-by-word reveals whose stagger is shorter than 2 frames. |
| 14 | `media_contract` | The file on disk matches what the spec promised: resolution, frame rate, duration. Catches "the render succeeded but produced the wrong video". |

### The rule that makes the gates trustworthy

A gate reporting a problem is **not** the same as the run being unshippable.
The difference is not guessed from the wording of the message — it is looked up
in a fixed registry (`colophon/qa/taxonomy.py`). Every run ends in one of three
states:

| Verdict | Meaning |
|---|---|
| `ready` | Nothing to report. |
| `ready_with_warnings` | Only advisories. Worth a reviewer's attention, still ships. |
| `blocked` | At least one blocker, **or something the registry does not recognise**. |

That last clause is the whole ballgame, and it is worth understanding properly.

A system that classifies problems by matching their *text* gets **more
permissive exactly when it is confused**: a new kind of problem matches no
rule, gets filed as "unknown but presumably minor", and ships. Inverting the
default fixes it. An unrecognised problem is not evidence that something is
safe — it is evidence that we do not know what it is — so it blocks.

Forgetting to register a code therefore costs you a blocked run, which you
notice immediately. The alternative costs you a shipped defect, which you
notice in production.

### Why the gates and the AI reviewer are separate

Research on visual QA by vision model (UI-Lens, CVPR 2026) found F1 scores of
11–42 on boundary defects. In plain terms: asking a model "is this video good?"
is close to a coin flip on exactly the subtle failures that matter most.

So a model may *comment* on taste, but it can **never alone trigger a repair**.
The deterministic gates hold the veto.

---

## Every command

Run `colophon <command> --help` for flags. In rough order of how you'd use them.

| Command | What it does | When you'd reach for it |
|---|---|---|
| `doctor` | Checks that node, npm, ffmpeg and ffprobe are present and reports their versions. | First thing, on a new machine. |
| `init` | Freezes a spec into a new run directory. | Starting a video. |
| `plan` | Lays the scenes onto the clock and prints the timeline. | "Why is my video 19s and not 22s?" |
| `validate` | Runs the 4 paper gates. No rendering. | Fast feedback while you're still drafting. |
| `emit` | Spec → editable HTML/CSS project. | You want to look at or hand-edit the markup. |
| `render` | Project → MP4. | You want the video. |
| `qa` | Runs all 14 gates. | You have a render and want the verdict. |
| `review` | Extracts frames and builds a contact sheet for a human or model to look at. | You want eyes on it, not just rules. |
| `record-review` | Validates an independent review and merges the verdicts with the gate results. | Feeding a reviewer's verdict back in. |
| `repair` | Applies targeted, validated edits to the spec. | You know what's wrong and want it fixed precisely. |
| `design` | Runs the repair loop: check, fix, re-check, up to a budget. | You want it fixed without hand-holding. |
| `deliver` | Everything above, end to end. | The normal path. |
| `resume` | Shows the last attempt matching the frozen spec and continues from there. | A run was interrupted. |
| `bench` | Compares colophon's judgement against a naive "it rendered, ship it" baseline — and optionally against real coding agents. | Proving the instrument works. |
| `mcp` | Serves colophon's pipeline as MCP tools over HTTP (`colophon mcp serve`). | You want an agent harness — TrueForge, say — to drive the gates in a loop. |

### Two commands that deserve a paragraph

**`design`** is the automatic repair loop. It looks at the failures, fixes the
ones that have an obvious mechanical fix (wrong duration, missing field), and
routes the genuinely judgement-based ones to a seam where a model could be
plugged in. It stops after a fixed budget, and it also stops early if it sees
the *same* set of blockers several turns running — that is the signal that it
is stuck, not that it needs more turns.

By default `design` only runs the four paper gates, because there is nothing
rendered yet. Add `--render` to have it actually emit, render, and check the
result on every turn. When it does that, it records **how far the checks
actually reached** — a spec the loop calls `ready` is ready *at the level it
was able to verify*, and the report says which level that was. It never
implies more than it checked.

**`bench`** answers "is our inspector actually better than nothing?" It runs
two artifacts — one we know is good, one we know has a subtle stutter — past
our gates and past a naive presence check. Our gates must accept the good one
and reject the broken one; the naive check accepts both.

The external rows (codex, claude) are **really wired and really do run** — but
only when you pass `--agents`. That is deliberate: running a coding agent
costs money, needs network and credentials, takes minutes, and cannot be
reproduced. A benchmark that quietly shells out to a paid API because someone
happened to have the binary installed is not a benchmark, it is a surprise
bill. So the default run is free, offline, and byte-for-byte repeatable.

An agent that fails to produce anything is reported as **SKIP with the
reason**, not as a failure. "codex scored 0/2" reads as a verdict on codex's
ability; "codex never ran — no network" is usually the truth. Conflating them
would publish a number that is really just a fact about the wifi.

---

## Running colophon inside an agent harness

Colophon is an instrument, not an employee. It reports what is wrong; it does
not decide what to do about it. Something has to read the report and act.

That "something" is an **agent harness** — the environment an agent works
inside: the loop that lets it take an action and look at the result, the tool
calling, the sandbox, the approvals, the session state. (It is the same sense
in which a coding assistant runs inside its own harness: the harness is the
runtime, and the model is only one part of it.)

Colophon plugs into one as an **MCP server**:

```
   ┌──────────────────────── agent harness (e.g. TrueForge) ───────────────┐
   │                                                                       │
   │   agent  ──calls──>  colophon tools  ──returns──>  blockers            │
   │     ▲                                                    │            │
   │     └────────── edits the spec, re-runs the gates ────────┘            │
   └───────────────────────────────────────────────────────────────────────┘
                                    │
                          HTTP (MCP), localhost
                                    │
                     colophon mcp serve  →  the 14 gates
```

Start the server, point the harness at it, and the agent picks up seven tools:

| Tool | What the agent gets back |
|---|---|
| `colophon_gates` | All 14 gates, what each checks, and what it needs before it can tell the truth. |
| `colophon_doctor` | Whether this machine has the runtime (node, ffmpeg, ffprobe). |
| `colophon_init` | A frozen run directory and the spec's hash. |
| `colophon_validate` | The 4 paper gates — cheap, no artifacts needed. The one to loop on. |
| `colophon_plan` | The timeline: when every scene starts and ends. |
| `colophon_qa` | All 14 gates on an attempt. |
| `colophon_design` | The bounded repair loop, and how far it got. |

Every answer has the same shape: a `state` (`blocked`, `ready_with_warnings`,
`ready`), a list of **blockers** naming the gate and the failure code, a list
of **warnings**, and a one-line `hint` telling the agent what to do next.

The hint exists because of a specific way agents get this wrong. Before an
artifact exists, several gates report *"nothing to check"* — and colophon
counts that as a blocker, because failing closed is the whole point. An agent
that doesn't know this reads the blocker as a defect it caused and starts
"fixing" a spec that was fine. The hint says out loud what a human would have
inferred: emit first, then re-read me.

Why the harness matters here: the loop is where the work happens. The agent is
not asking a model "is this video good?" — a coin flip on exactly the subtle
failures that matter. It is calling a deterministic instrument, reading a
precise answer, and acting on it. The harness supplies the loop; colophon
supplies the ground truth.

---

## The four places you can swap something out

Colophon is built so that the parts most likely to change are behind a seam.
Each one has a working default and a documented interface.

| Seam | Default | What you'd swap in |
|---|---|---|
| **Renderer** | The HTML/CSS adapter | A different way to turn a spec into pixels. The renderer is the *only* place in the codebase allowed to know what HTML and CSS are. |
| **Reviewer** | Contact sheet + recorded verdicts | A different critic — human, a different model, a different rubric. |
| **Repair agent** | Not wired. Mechanical fixes run; judgement calls stop the loop and report. | A model that proposes spec edits. Deliberately off by default: an agent that silently rewrites your spec is worse than one that admits it is stuck. |
| **Bench agent** | SKIP unless `--agents` | Another coding agent to compare against. |

The principle behind all four: **an agent runtime is a caller, not a
dependency.** The pipeline runs to completion with the agent bridge deleted,
and it runs to completion with the repair loop deleted. Optional machinery must
be genuinely optional.

---

## Where everything lives

One line each. If you only remember this table, you can find your way around.

| Package | What lives there |
|---|---|
| `spec/` | The spec schema, loading, validation, and hashing. Source of truth. |
| `content/` | What the video is allowed to say — claims and grounding. |
| `timeline/` | When things happen. Seconds in, frames out. |
| `presentation/` | How things look — scene roles and motion treatments. |
| `assets/` | Brand colour tokens and the local asset registry. |
| `renderers/` | The only place that knows about HTML and CSS. Adapter seam. |
| `qa/` | The 14 gates, the run-report machinery, and the failure-code registry. |
| `review/` | Frame extraction, contact sheets, and independent critic verdicts. |
| `repair/` | Applying targeted spec edits, with a proof that they stayed local. |
| `harness/` | The repair loop, and the render driver that feeds real artifacts into it. |
| `bench/` | Comparing colophon's judgement against other harnesses. |
| `runs/` | Run directory layout, attempt numbering, manifests, recovery. |
| `runtime/` | Finding and pinning node/npm/ffmpeg/ffprobe so a run is reproducible. |
| `qa/pipeline.py` | The 14-gate catalog and the two canonical gate sets, derived not hand-listed. |
| `adapters/agent/` | Optional translation helpers for an agent driving colophon. Deletable. |
| `mcp_server.py` | The same pipeline exposed as MCP tools over HTTP, for an agent harness. Needs `pip install '.[mcp]'`. |

---

## Glossary

Terms decoded in plain English, with the concrete example from this project.

**Spec.** The recipe. A JSON file describing the video: its scenes, timing,
text, colours. The single source of truth; everything else is derived.

**Emit.** Turning the spec into an editable HTML/CSS project, *before*
rendering. Lets you inspect the markup, and lets gates check it without paying
for an encode.

**Render.** Turning the project into an MP4.

**Attempt.** One numbered try inside a run directory. Attempts are disposable;
the spec is not.

**Gate.** One deterministic check. Pass or fail, with reasons. No opinions.

**Stage.** The code that implements a gate.

**Blocker vs advisory.** A blocker stops the run. An advisory is worth
reading but still ships.

**Fails closed.** When in doubt, say "stop" rather than "go". An unrecognised
problem blocks rather than being waved through. See
[the rule that makes the gates trustworthy](#the-rule-that-makes-the-gates-trustworthy).

**Taxonomy.** The fixed registry of failure codes and their severities. If a
problem's code isn't in it, the run blocks.

**Grounding.** Every claim on screen must trace back to a source you supplied.
Nothing is invented at render time — treatments can only arrange the copy you
gave them, which makes an unbound number structurally impossible rather than
merely detected after the fact.

**Treatment.** A named motion behaviour for a scene (a word-by-word sweep, a
thinking pulse). Bounded set, each with preconditions.

**Role.** What a scene is *for* — hook, problem, solution, proof, call to
action. Roles have a sensible order; gate 3 checks you didn't put the call to
action first.

**Canvas audit.** The check that the background colour is right. It walks
*ancestors only*, so a clip's own background must be the brand colour while its
children are free to vary — that is where legitimate visual variety lives.

**Contact sheet.** A grid of still frames pulled from the video, so a human or
model can review it without scrubbing a timeline.

**Frame vs second.** Colophon authors in **seconds**; frame rates are a
renderer concern. This survives an fps change, whereas hardcoding
`TITLE_HOLD_FRAMES = 100` silently means something different the moment you
switch to 60fps.

**Authored vs timeline duration.** The *authored* total is the sum of scene
lengths. The *timeline* total is what the composition actually runs, which is
shorter when scenes overlap at their boundaries. The timeline total is the
delivery baseline, because it is what ships.

**Deterministic.** Same input, same output, every time. Why the gates can be
trusted and a model's opinion cannot.

**Provenance.** The record of what produced what. Every report carries the
spec's hash, so "which spec made this video?" is always answerable.

**Harness.** The *environment an agent works inside* — the loop that lets it act
and look again, the tool calling, the sandbox it is allowed to touch, the
approval prompts, and the memory of what happened earlier in the session. It is
**not** the model. The model is the thing that thinks; the harness is the room
it thinks in, with the doors and the tools.

  *Concrete example:* when you chat to a coding assistant in its app, the app
  is the harness. It decides whether the assistant may edit your files, it
  remembers the conversation, and it keeps handing the assistant the results of
  whatever it just did. Swap the model underneath and the app still works.
  Colophon is the same idea for video: it owns the loop and the verdict, and a
  harness is where you park an agent to drive it.

**Runtime.** Whatever is actually executing the agent right now. TrueForge is
today's runtime for colophon. It is swappable — anything that can make an HTTP
call to the MCP server can drive the gates, and colophon runs to completion
with every runtime deleted. See [ADR 0010](adr/0010-the-harness-is-a-seam-not-a-product.md).

**MCP.** Model Context Protocol. A standard way for an agent to call a tool
over HTTP and get structured JSON back. Colophon serves its seven tools this
way, which is why any MCP-speaking client can drive it. Colophon uses HTTP
rather than a subprocess because TrueForge's MCP client only supports remote
servers.

**API key.** Needed for the **model**, not for the harness and not for the
gates. TrueForge starts with no key; colophon's 14 gates make zero model calls.
The cost begins the moment you ask a model to read a verdict and decide what to
do about it.

**Seam.** A deliberately narrow joining point where one implementation can be
swapped for another without the rest of the system noticing.

**Live agent row.** A bench result that came from really running codex or
claude. Marked with `*` in the table, because it is a record of one real
attempt, not a reproducible number.
