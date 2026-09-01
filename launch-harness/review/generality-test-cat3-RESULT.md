# Category 3 generality test — RESULT

**Date:** 2026-09-01
**Verdict:** **PASS — first true pass of the generality test.**

## What was tested

The harness's actual claim: that a brief for a product the agent has never seen
will produce a video, with **no starter file, no .tsx, no render.json, no scene
graph**. The test fixture is a product called **Plink** that did not exist in
the project before this work.

## The two test artifacts (the entire input)

- `./review/generality-test-brief.md` — the brief
- `./tools/generic-template-pipeline.md` — the doc

The doc was authored so that a fresh agent reading only it could build a working
composition. The brief was authored so that any product in that shape would
exercise the same code path.

## How the test was run

A fresh sub-agent was spawned in an isolated context with strict instructions:

> You may read ONLY two files. Do not read the existing TSX. Do not read any
> existing brief.json. Follow the doc and render the Plink video.

The sub-agent did this. It:
- Read the two files.
- Wrote `brief.json` (the doc told it where, though it had to guess the path —
  now stated explicitly).
- Ran `npm install` and `npm run render`.
- Verified the output (ffprobe, OCR, leak gate, root opacity).

It produced a real Plink video. **No source-code reads, no scene-graph
authoring.**

## What the sub-agent's report proved

| Check | Result |
|---|---|
| Real Plink content at frame 20 (title scene) | "INTRODUCING / Plink / Turn your daily habits into a pinball game you actually want to play" |
| Real Plink content at frame 150 (feature scene) | "What Plink does / 1 Daily routines become pinball launches / 2 Streaks unlock multiball / 3 Friends' boards sync every week" |
| Real Plink content at frame 260 (CTA scene) | "Get Plink / plink.app / Plink" |
| RankPal leak (`--grep rankpal`) | 0 matches across 3 stills, exit 0 |
| Plink positive control (`--grep plink`) | 3/3 matches, exit 1 (gate mechanics confirmed) |
| Root pixel (5,5) | (255, 255, 255) — opaque white, alpha 255 |
| ffprobe | h264 1920×1080, 300 frames, 10.048s, 828 kB; aac 48000 Hz stereo, 471 frames, mean/max volume −91.0 dB |
| Total npm install | 255 packages, 27s (doc said ~184; actual 255 — minor) |
| Total setup | nothing else (no API keys, no env vars, no manual config) |

## What was repaired between the failed first attempt and this pass

| # | Repair | Why |
|---|---|---|
| 1 | `TitleScene` / `FeatureScene` / `CtaScene` now require a `backgroundColor` prop; each `Frame` is opaque | The 57.24 content-diff pop at f221→f222 (near-hard cut). Transparent overlays vanish when their Sequence ends. |
| 2 | Scene hold = solo + XF_FRAMES + 1 (was solo + XF_FRAMES) | Off-by-one: the incoming scene reaches opacity 1 on the +1 frame, so the outgoing scene must be present on that frame. |
| 3 | Feature bullet slide-in 28px/22 frames → 22px/28 frames | First pass peaked at 27.75 content-diff (above the 2–25 gradual band). |
| 4 | 16px accent dots → 56px numbered accent chips | Feature scene accent coverage 0.07% → 0.34%, into the same order as title (0.90%) and CTA (1.61%). |
| 5 | Feature bullet column flex: 1, max-width 1200, text node flex: 1 | First pass wrapped each feature per-word because the column collapsed to content width with no screenshot. |
| 6 | CTA pill spring delay removed (`frame - 6` → `frame`) | First pass: f208→f216 content-diff 0.00 — incoming contributed nothing for 6 frames of its own dissolve. |

## Doc defects surfaced by the test (and fixed)

| # | Defect | Fix |
|---|---|---|
| 1 | "Silent cut (no audio)" — false; an AAC stream exists at −91.0 dB | Re-stated as "silent cut — a stream exists but is not meant to be heard" |
| 2 | `brief.json` path not stated in the doc | Stated explicitly: engine root, sibling to package.json |
| 3 | Stray trailing `--` in §8's `npm run still` example | Removed |
| 4 | Brief's filename pointer said `tools/remotion-pipeline.md` (a different, RankPal-targeted doc) | Updated to `tools/generic-template-pipeline.md` |

## What this proves

The harness's claim is now empirically supported: a brief alone, through the
doc, produces a working MP4 for a product the harness has never touched. The
doc is sufficient. The engine is general. This is **the first true pass** of
the generality test.

## Open work (not in this test's scope)

- **Category 2 generality test** — blocked on real footage. The user is
  providing a real ~10s screen recording + one narration line. When that
  arrives, route it through `the footage client-editor.md` and run the same gate.
- **RankPal** remains frozen. All staged changes are still uncommitted
  (HEAD `81491f43`); do not commit/push without instruction.
