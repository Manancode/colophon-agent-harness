---
name: launch-video
description: >-
  Turn a product-launch brief into a finished launch video using your own coding
  agent as the brain — no LLM key, no server of ours. One explicit branch at the
  front door (is there footage, yes or no), one local render path each way, then
  an 8-dimension review gate the agent has to pass before it can ship.
version: 0.3.0
---

# Launch video harness

You are the brain. This skill is the hands.

There is no LLM key here and no server that holds one. You do the thinking with
the subscription the user already pays for. This skill points you at a local
render path and then makes you grade your own work before you show it.

> **Design principle:** this is an *agent-native tool*, not a hosted video
> service. The user's agent supplies all intelligence. We supply the routing,
> the render runtime, and the QA checklist.

```
launch-harness/
  SKILL.md          <- you are here: the branch + the gate
  review/criteria.md <- the gate you must pass before shipping
```

---

## Step 0 — The branch (there is exactly one)

This is the only routing decision in the whole harness, and it is **a fact about
the input, not a judgement call**. Never ask the user which path to take — look
in the folder.

```bash
find . -maxdepth 2 -type f \
  \( -iname "*.mp4" -o -iname "*.mov" -o -iname "*.mkv" -o -iname "*.avi" \
     -o -iname "*.webm" -o -iname "*.wav" -o -iname "*.mp3" -o -iname "*.m4a" \)
```

| Result | Path | Why |
|---|---|---|
| **Zero media files** | **Path B — composition only** | Nothing to cut. Build the video from the brief. |
| **One or more** | **Path A — cut the footage** | Real media has to be arranged and trimmed. |

### Why the branch lives here

Measured, not assumed. The footage toolkit has **no zero-footage path**: pointed
at a folder with no media, its transcription batch step exits `1` with
`no videos found`, and nothing downstream recovers from that. It does not
degrade into a composition-only run, and it does not hand off to anything.

So the branch cannot live inside the toolkit. It has to happen one layer up,
before the toolkit is ever invoked. That is what this step is. Full evidence —
commands, exit codes, and the skill-text grep — in
`review/empty-footage-test-2026-09-01.md`.

**Do not skip this step.** If you invoke the footage toolkit on an empty folder
you will get a hard error and waste the run.

---

## Path A — footage present → cut it

You are now driving the footage toolkit from its own `SKILL.md`. Read that; it
is the source of truth for this path. Summary of what it will do:

1. **Inventory** — `ffprobe` every source, transcribe the directory, pack the
   phrase-level transcript.
2. **Pre-scan** — note verbal slips and mis-speaks before planning.
3. **Converse** — describe the material in plain English, ask questions shaped
   by what you actually see.
4. **Propose a strategy** — 4–8 sentences. **Wait for confirmation.**
5. **Execute** — build the cut list, cut on word boundaries, grade, composite.
6. **Preview**, then **self-eval** on the rendered output before showing it.

Non-negotiables worth restating here because they cause silent breakage:

- Cut on **word boundaries**, never mid-word.
- Pad every cut edge (working window 30–200ms).
- 30ms audio fades at every segment boundary, or you get audible pops.
- **Subtitles go on LAST**, after every overlay, or the overlays hide them.
- Word-level verbatim transcription only — never phrase-level.

When this path needs motion graphics or an overlay, it calls the composition
engine as a sub-step, scoped to a single animation slot. That is the toolkit's
job to decide, not yours.

---

## Path B — no footage → compose it

Nothing to cut, so don't pretend otherwise. Hand the brief to the launch
composition workflow and build the video as a composition: capture or author the
visuals, derive a design system, storyboard it, build the frames, render.

Do not invent a transcript, do not synthesise footage, and do not silently
downgrade into "here's a slideshow." The brief is the source material.

Work in `videos/<project>/`, named from the brand in kebab-case. Output lands at
`renders/video.mp4`.

---

## Step 1 — Review gate (mandatory, before you say "done")

Follow **`review/criteria.md`**. Summary:

1. Score all **8 dimensions** 1–5:
   `hook_and_value_clarity` · `product_capability_accuracy` ·
   `brand_consistency_and_visual_craft` · `motion_continuity_and_pacing` ·
   `narration_quality_and_audio` ·
   `subtitle_readability_and_optional_playback` ·
   `launch_readiness_and_call_to_action` · `brief_length_match`
2. **Every applicable dimension must independently be ≥ 4.** An average cannot
   compensate. One `2` is a fail.
3. Any dimension < 4 → revise *that dimension*, re-render, re-score.
   **Retry budget: 3 attempts.** Then stop and flag the human with the blocking
   dimension and what you need. Do not loop forever.
4. Emit the JSON score block from `review/criteria.md` §5.

### The honesty rule

**Never claim you looked at an image.** Back every score with structural
evidence (read the source), pixel evidence (sample the PNG with PIL), media
evidence (`ffprobe`), or text evidence (OCR the rendered frames). "It looks
good" is not evidence.

Two traps that have burned us before:

- A negative OCR result only counts if the same pass **did** find other text in
  those frames. An OCR run that finds nothing at all is a broken pass, not a
  pass.
- **N/A is not an escape hatch.** `n/a` is valid only when the *brief* didn't
  ask for it, and it needs a written reason.

---

## Step 2 — Handoff

Present the artifact **and the score block together**. The user's standard:

> Show me the artifact and the numbers, not a description of the process.

If the verdict is `fail` or `needs_visual_review`, say so plainly and name the
blocking dimension. **Do not present a failing video as done.**
