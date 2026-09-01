# Generality test — Category 3 finding (NOT a pass)

**Date:** 2026-09-01
**Test identity:** the pivotal "Stop — we validated the wrong thing" directive.
The prior 5 attempts all fixed bugs in a file that already had RankPal's finished
composition baked in. This test asks the real product question: *can the harness
take a brief for a product it has never seen and produce a video with no starter
file?*

**Verdict: FAIL.** The harness cannot. It is a RankPal-specific render consumer,
not a from-brief builder. Every "clean pass" in attempts 1–5 validated the wrong
thing.

---

## The brief (only input the doc-only agent received)

See `generality-test-brief.md`. Product **Plink** — invented, never touched by
this agent. Input = name + one-line description + brand color `#7C5CFF` + a 3-item
feature list. **No `.tsx`, no `render.json`, no scene graph.** The agent was
permitted to read **only** `tools/remotion-pipeline.md`.

## Method (faithful to the directive)

- Read `tools/remotion-pipeline.md` **alone** (no other context).
- Built in a **scratch copy** (`/tmp/harness-gen-test`, `node_modules` symlinked
  from the original) so RankPal's frozen files were never touched. The original
  `render.json` (RankPal's) was **overwritten** with what a doc-only agent could
  plausibly produce: only what the doc tells it exists (`document.fps/width/height`).
- Ran `npm run extract`, then `npm run render`, exactly as the doc instructs.

## Result: it rendered a 670-frame, 22.4s MP4 that is 100% blank

- `ffprobe`: `codec=h264, 1080x1920, nb_frames=670, duration=22.378667s` — a
  valid file, but empty.
- Pixel sample of frames 45 and 300 (PIL): mean RGB **(255, 255, 255)**,
  **0.00% non-white** pixels, **0** pixels near Plink's violet `#7C5CFF`.
- macOS Vision OCR: **0 text blocks** in either frame — no "Plink", no copy at all.

The artifact: `generality-cat3-blank.mp4` + `generality-cat3-blank-f45.png` /
`-f300.png`.

## Exactly where it broke

**1. The doc gives no authoring surface (doc gap).**
`remotion-pipeline.md` line 10–12: *"A Remotion project whose composition is
driven by a the launch-spec format scene-graph export (`render.json`)."* It presupposes
`render.json` already exists. The only "authoring" line (61) is a bare one-liner —
*"Author changes go into `render.json` (or a bespoke TSX composition)"* — with no
schema, no procedure, no component API. The doc never mentions `layers`, `clips`,
or `bundledJs`. A doc-only agent literally cannot construct a valid `render.json`.

**2. `extract` is a pure consumer of an undocumented upstream (architectural).**
`scripts/extract-launchspec-scenes.mjs` lines 13–16 read
`clip.props.browserAgentOutput.bundledJs`. That embedded JS **is** the scene
content, and it is produced by an upstream "the launch-spec format" agent that **no doc
describes how to invoke.** On the doc-only `render.json`, extract reports:

```
Extracted 0 embedded the launch-spec format scenes
```

`scene-registry.ts` is written as an empty object. There is nothing to render.

**3. The composition is RankPal-locked and self-gates on RankPal's exact layout
(architectural — the decisive break).**
`src/LaunchSpecJson.tsx` is not generic:
- Line 87: `export const launchspecDurationInFrames = 670;` — duration hardcoded,
  not read from `render.json`.
- Lines 73/75: `DRAFT_PROMPT_TEXT` / `COMPETITOR_PROMPT_TEXT = 'Use @rankpal to
  show what a competitor app shipped today'` — hardcoded RankPal copy.
- Lines 300–346: `RankPalTitleScene` renders `Introducing <span>RankPal</span>`.
- Lines 1715–1719: the component early-returns a **blank white fill** unless
  `render.json` contains a clip with `startFrame === 0 && durationInFrames === 121`
  — i.e. RankPal's exact scene layout:

  ```js
  const titleClip = clips.find((clip) => clip.startFrame === 0 && clip.durationInFrames === 121);
  if (!titleClip) {
    return <AbsoluteFill style={{backgroundColor: '#ffffff'}} />;  // BLANK
  }
  ```

So even a *well-formed* non-RankPal `render.json` either renders blank (layout
doesn't match) or, if it did reach the hardcoded scenes, would render **RankPal**,
not the new product. The hardcoded `RankPalTitleScene` / `RankPalChangesScene` /
`RankPalDraftReadyScene` are unreachable dead code without RankPal's specific
`render.json`.

**4. Observable outcome (evidence).** The doc-only render is a 100% white,
text-free 22.4s MP4. No product content of any kind for "Plink".

## Why attempts 1–5 "passed" and this failed

Every prior fix (whoosh level, hook accent, loudnorm master, mid cue) was applied
to `LaunchSpecJson.tsx` — a file carrying RankPal's finished composition and
RankPal's `render.json`. The gate scored the *output* of a pre-baked,
product-specific pipeline. It never tested whether the harness could *originate* a
composition for an unseen product from a bare brief. It can't. The "harness" was a
script wearing a harness costume.

## Category 2 status (separate engine, different blocker)

`the footage client` **is installed and the the local footage tool app is running**
(`the footage client context` → `projectDir: "~/Desktop/color-test"`). Its doc
(`the footage client-editor.md`) actually documents an authoring mechanism — you hand-write JSX,
the app recompiles, `@inspect` consts are the control contract. So Category 2 is
*architecturally* more honest than Category 3.

The Cat 2 test as specified **cannot be executed here** because it requires a
**starter asset the brief alone can't supply**: a screen recording / short clip
of the new product plus a narration line. No such footage for "Plink" exists and
I will not fabricate it. This is an *input* blocker, not the structural gap that
kills Category 3.

## What "harness" would actually require (recommendation, not yet done)

To truthfully claim "takes a brief for an unseen product → video with no starter
file", the Category 3 engine needs one of:
- A **documented brief→`render.json` (with `bundledJs`) generator** — the missing
  "brain-to-composition" step. Currently that step is an undocumented upstream
  "the launch-spec format" agent.
- OR a **generic, data-driven composition component** that reads the brief
  (product name, color, features) instead of the hardcoded RankPal copy and is
  not gated on a specific `startFrame/durationInFrames` clip layout.

Until then, the honest label is: *RankPal launch-video renderer (one product)*,
not *general launch-video harness*.

## Evidence index

- `generality-test-brief.md` — the only input.
- `generality-cat3-blank.mp4` — the doc-only render (100% white, 22.4s).
- `generality-cat3-blank-f45.png` / `-f300.png` — blank frames (OCR: 0 text).
- Live outputs quoted above: `Extracted 0 embedded the launch-spec format scenes`;
  mean RGB (255,255,255), 0% non-white; `launchspecDurationInFrames = 670`.
