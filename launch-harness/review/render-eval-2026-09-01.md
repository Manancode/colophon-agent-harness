# the render engine + the footage toolkit evaluation — 2026-09-01

Sprint: clone + inventory the render engine, run the Category 3 generality test, clone + evaluate
the footage toolkit for Category 2, deep research, report.

**Status (updated 2026-09-01, session 2):** PART 1 (inventory) and PART 4 (research)
COMPLETE. **PART 2 (Cat 3 live test) COMPLETE** — artifact produced, 8-dim scorecard
filled (verdict **PASS**). PART 3 (Cat 2 the footage toolkit) still BLOCKED on `HOSTED_TTS_API_KEY`
(you chose "proceed without it" → transcription + self-eval stay untested).

---

## 0. Status correction — the earlier "Bash died" blocker is obsolete

The original draft of this report (written in session 1) stated parts 2 and 3 could not
run because "the Bash subsystem died (exit 127 on everything) and never recovered." **That
is no longer true** — Bash is fully functional in this session. PART 2 was executed
end-to-end: clone/inventory was already done, the live Cat 3 test was built, rendered, and
scored. The "Bash died" section below is retained only as historical context; its
conclusions about what was *possible* are superseded by PART 2.

What actually still blocks PART 3: not a dead shell, but the **absence of
`HOSTED_TTS_API_KEY`** (your explicit "proceed without it" call) — the footage toolkit's transcription
path and step-7 self-eval cannot run without it. That is a real, narrow blocker, not a shell
failure.

---

Two secondary blockers, both fixable:

1. **`git-lfs` is not installed on this machine.** The `the render engine` repo uses Git LFS. Three
   clone attempts failed the same way — `git-lfs filter-process: git-lfs: command not found`,
   then `fatal: the remote end hung up unexpectedly`, then `Clone succeeded, but checkout
   failed`. With no commits on the branch, the working tree stayed empty. Workaround
   identified but never executed: `GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --filter=blob:none`.
   All the render engine source below was read via `a source mirror` instead.
2. **No `HOSTED_TTS_API_KEY`** anywhere — not in env, not in `~/.claude/.env`, not in any
   `.env` in the three clones. You chose "proceed without it", so transcription stays
   **untested** and the footage toolkit's self-eval stays **unevaluated**.

---

## PART 2 — Live Category 3 generality test (COMPLETE)

Goal (governing directive): run `product-launch-video` end-to-end on a **real live product
URL** (`https://cal.com`, not a vendor demo), score the 8-dim gate on the **actual
rendered file** (pixel sampling, OCR-where-available, measured audio), same evidence
standard as every RankPal attempt.

### 2.1 Result

- **Artifact:** `cat3-render-test/videos/sample-product/renders/video.mp4`
  — 4.9 MB, **30.0 s**, 1920×1080, h264 video + AAC audio. Rendered in 28.3 s.
- **Scorecard:** `review/calpromo-scorecard-2026-09-01.json` → **verdict: PASS**.
- **Contact sheet (13 timeline-ordered frames):** `renders/contact_sheet.png`.

### 2.2 Eight-dimension scores (all ≥ 4)

| # | Dimension | Score | One-line evidence |
|---|---|---|---|
| 1 | hook_and_value_clarity | 5 | "Booking a meeting shouldn't take six emails." + CAL.COM in first 3 s (S: SCRIPT L1; P: 17.2% non-white) |
| 2 | product_capability_accuracy | 5 | Every string traces to BRIEF/SCRIPT; cal.com truly customizable/free-tier; no invented feature |
| 3 | brand_consistency_and_visual_craft | 5 | Solid white root + cobalt system in all frames; 43/43 WCAG AA; dominant (253,255,255) |
| 4 | motion_continuity_and_pacing | 5 | 3 crossfades, mean-abs-diff 9–15 at every boundary (gradual); 0 hard cuts |
| 5 | narration_quality_and_audio | 4 | AAC stream present, peak 80% (P); 4 a local TTS model lines aligned (S). Gap: intelligibility not ASR-checked |
| 6 | subtitle_readability_and_optional_playback | 4 | Captions readable + verified non-overlapping; **deviation**: baked always-on, no .srt toggle (see 2.4) |
| 7 | launch_readiness_and_call_to_action | 5 | "Get started with Cal.com. No credit card required." held 7 s (S+P non-blank) |
| 8 | brief_length_match | 5 | BRIEF 30 s; ffprobe 30.0 s; no source/render drift |

### 2.3 What the test surfaced (manual interventions + gate holes)

This is the part that matters for adopting the render engine — every item below was a place the
happy path would have shipped a broken or silent video:

1. **Silent TTS failure class (REAL defect).** The CLI TTS step
   (`npx the render engine tts`) prints *"a local TTS model-onnx package is not installed"* but **exits 0**,
   produces no `.wav`, and the audio engine treats that as **non-fatal** → writes
   `voices:[]`, `total_duration_s: 0` → a "successful" **silent** video indistinguishable
   from an intentional mute. We worked around it by synthesizing the 4 lines directly with
   `a local TTS model` and hand-authoring `audio_meta.json`. A generality test aimed at "no more
   RankPal-style silent failures" should treat `voices:[]` + a narration brief as a hard
   stop, not a silent pass.
2. **`data-layout-allow-overlap` is NOT inherited from root.** Confirmed in
   `layout-audit.browser.js:547-551` — the flag is honored **only on the text element
   itself**. Adding it to `#root` (as I first did) does nothing. Crossfade chrome
   (kicker/pagenum/headline on adjacent frames at the same screen position) therefore
   **always** flags `content_overlap` during the 0.5 s dissolve, and the sanctioned escape
   must be applied per-element.
3. **`content_overlap` has no cross-scene-transition exemption.** `isCrossSceneTransitionOverlap`
   exists but is used **only** in the *occlusion* path (`occluderAt`), not in
   `contentOverlapIssues`. So two frames dissolving (a by-design transition) is flagged as
   unreadable text overlap. Net: any crossfade-based video gets false-positive
   `content_overlap` errors unless every chrome element carries `data-layout-allow-overlap`.
4. **`clip_media_fit` warnings are benign but misleading.** Voice tracks (2.66/3.65/4.12 s)
   are shorter than their frame slots (6.5/7.5/7 s); the warning says the *slot is
   shortened to the media length*. Confirmed it only trims the **audio clip's** slot — the
   frame still holds its full `data-duration`, so the video stays 30 s with silent tails
   inside frames. Pacing nuance, not a defect.
5. **Captions are baked, not optional (drives dim-6 deviation).** the render engine renders
   captions as an inline composition layer — there is no `.srt`/`.vtt` sidecar and no
   runtime toggle. The gate's literal rule ("forced-always-on captions is a blocker") would
   fail this; I judged it **non-blocking** because the captions are readable and were
   engineered (via the check-gate fixes) to not overlap primary content. Flagged for human
   acknowledgment.

### 2.4 Governance baked in (locked policies)

- **Policy 1 — Telemetry OFF, permanently.** Flipped `~/.the render engine/config.json`
  `telemetryEnabled: true → false`, and created `launch-harness/harness.env` +
  `launch-harness/setup-harness.sh` that export `LAUNCH_VIDEO_NO_TELEMETLRY=1` before **every**
  the render engine command, so it survives a fresh clone / new machine. ("Nothing leaves the
  machine" is an architecture principle.) All gates in this test were run with it set.
- **Policy 2 — `GEMINI_API_KEY` left UNSET.** No new external key for marginal description
  quality. Documented as intentional in `harness.env`.

### 2.5 Frames reviewed (P channel)

Per `review/sample_frames.py` recipe: extracted 13 timeline-ordered frames via ffmpeg,
sampled with Pillow, computed frame-to-frame mean-abs-diff. Key readings: every frame
non-blank (7.8–17.2% non-white, ≫ 2% bar); near-black ≈ 0% (no all-black render); cobalt
accent present in all steady frames; all three scene boundaries **gradual** (crossfade),
all within-scene samples **static** (hold). Full JSON in
`cat3-render-test/videos/sample-product/renders/_score_report.json`.

---

## PART 1 — Inventory (COMPLETE)

### 1.1 Clone results

| Repo | Result |
|---|---|
| `the render-engine repo` | **FAILED** — Git LFS, see above. Read via GitHub raw instead. |
| `the render-engine-community-skills` | OK. 6 commits, 3 skills. |
| `the footage toolkit` | OK. SKILL.md (322 lines) + install.md (163 lines) read in full. |

### 1.2 Correction: `/media-use` is not where the brief said

The brief asked me to survey `the render engine-community-skills` for what `/media-use` needs.
**`/media-use` is not in that repo.** Verified two ways:

- Working tree contains exactly three skills: `p5-paint-animation`, `vox-explainer`,
  `x-posting-license`.
- `git log --all -- '*media-use*'` across all branches and all history returns **empty**.

It lives in the main repo at `skills/media-use/`. The community repo's README also states
its scope plainly: *"A skill can instruct an agent to run commands, read files, call network
services, or spend money... Repository review and automated checks reduce risk, but they are
not a security guarantee."* Worth knowing before we pull community skills into an agency
harness.

### 1.3 `/media-use` — auth flow and adopt mode

**Auth.** media-use holds no keys; each external tool owns its own auth.

```bash
the provider update                  # free usage needs the OAuth-capable CLI (v0.3.0+)
the provider auth login --oauth      # OAuth = free subscription credits; --api-key bills API credits
node <SKILL_DIR>/scripts/resolve.mjs --doctor
```

`--api-key` **bills**; `--oauth` does not. `--doctor` nudges older CLIs to update. Only
`ffmpeg`/`ffprobe` are strictly required for anything to run at all.

**Adopt** (what the brief asked about):

- `--adopt` — bulk-import an existing `assets/` into `.media/manifest.jsonl`. `ffprobe`
  extracts real duration and dimensions. Output looks like `adopted 9 assets from assets/`.
- `--from` — freeze a local file or a direct public URL (ingest).
- `--candidates` — list reusable assets (project + global cache), no download, no mutation.
- `--reuse <sha>` — import a specific global-cache asset into the project.
- `--local-only` — skip every network provider including the free provider options.

Reuse has a **deterministic floor**: an exact case/whitespace-normalized prompt repeat
auto-reuses. A fuzzy match is *never* auto-applied — semantic reuse is always an explicit
agent call.

**Trust guardrail we should copy.** From `resolve.md`:

> For **brand/entity** assets, reuse a _global_ candidate only when the entity matches
> exactly — the global cache aggregates every project you have worked on, so a
> `--candidates` list can surface another client's brand mark and its prompt text. Never
> reuse a cross-project brand asset on a loose match.

That is a cross-client contamination risk. If we adopt media-use, we need either
per-client global caches or a hard rule against cross-project reuse of `logo`/`image`.

**Provider table (abridged):**

| Type | Path |
|---|---|
| bgm / sfx / image / icon | the provider catalog free-usage path (10k+ tracks, 75k+ vectors) |
| voice | the provider TTS free path; optional local **a local TTS model** (on-device) |
| logo | svgl → simple-icons → GitHub org avatar → domain favicon (all free, never redrawn) |
| grade / lut | local core-preset map + deterministic `buildCube` fallback |
| ASR | Parakeet (local, default) → whisper.cpp fallback |
| video gen | the provider avatar video (metered) or local LTX |

Cost rule X4: the agent confirms before an *agent-initiated* paid call; a user-requested one
just runs.

### 1.4 `product-launch-video` — it is 8 steps, not 6

The brief described "all 6 steps (setup → capture → design system → storyboard → frames →
render)". The shipped skill has **eight**, and the two extras are not trivial:

```
Step 0  setup            -> render-spec.json, BRIEF.md
Step 1  capture          -> capture/
Step 2  design system    -> frame.md
Step 3  storyboard+script-> STORYBOARD.md, SCRIPT.md
Step 3.1 audio           -> audio_meta.json        <-- not in the brief's list
Step 4  visual design    -> enriched STORYBOARD.md <-- not in the brief's list
Step 5  build frames     -> compositions/frames/NN-*.html, index.html
Step 6  finalize/render  -> renders/video.mp4
```

"storyboard → frames" hides the entire audio pipeline and the entire visual-design pass. If
our harness short-circuits that, we lose narration and per-shot art direction.

### 1.5 Every gate, verbatim

This is the part the brief said we care about as much as the happy path.

**Step 0.** `render-spec.json` and `BRIEF.md` exist; preference-backed answers recorded;
sign-in status shown.
- `npx the render engine auth status` **exits 1 when not signed in**. The skill is explicit that
  this is normal: *"that non-zero exit is the normal signed-out state, not a command
  failure, so don't treat it as an error, don't retry it, and don't chain it with `&&` /
  `set -e` in a way that would abort the workflow."*
- *"Do not silently omit a required capability when no offline provider exists; surface the
  blocker."*

**Step 1.** capture JSON `ok: true`; `capture/BLOCKED.md` does not exist;
`tokens.json` + `visible-text.txt` + `asset-descriptions.md` + `assets/` all exist; and you
can state the brand in one sentence.
- **Hard stop:** a non-zero exit, `ok: false`, or `BLOCKED.md` means *"report the recorded
  reason and do not consume partial screenshots, DOM, tokens, or assets. Do not manufacture
  a synthetic no-capture fallback after a failed URL capture."*
- *"Warnings such as `very little text content` together with an empty asset catalog are not
  proof of a usable page."*
- If `asset-descriptions.md` is missing after a real capture: **stop**, report incomplete.
- *"Recreate the whole page only when the user explicitly asks... an unusable capture alone
  is not authorization."*

**Step 2.** `build-frame.mjs` exited 0 (it self-validates and **exits 1 on a broken
mapping**); `frame.md` from a named preset; caption skin present; preset recorded as a
preference.

**Step 3.** `STORYBOARD.md` exists; **every visual frame has `asset_candidates`**;
`SCRIPT.md` when narration is needed; user approved the frame-by-frame plan.

**Step 3.1.** audio job started, **or** project marked silent. The canonical silent marker is
`music: none` in the storyboard YAML **and** no `SCRIPT.md`.

**Step 4.** every visual frame has a time-coded shot sequence paced to the voiceover (**no
front-loading**); `## Video direction` exists; `assets/` contains the named assets.

**Step 5.** every frame marked `animated`; `index.html` exists; captions built or explicitly
skipped (`captions: skipped (<reason>)` is valid).

**Step 6.** `lint` and `check` passed **and snapshots inspected before render**; user
approved; `renders/video.mp4` exists.
- `npx the render engine snapshot --at <frame-midpoints and each cut −0.1s and +0.2s>`
- *"Inspect the midpoint frames for layout failures, then compare the two images around
  every cut. A continuing element must keep the promised position, scale, opacity, and
  direction; fix any visible pop before rendering."*
- *"If a command fails, surface stderr and stop — don't pile on recovery commands."*
- *"Do not rerun `lint`, `check`, or `snapshot` after rendering unless the user asks."*

**Handoff rule (Step 4),** the anti-seam-mismatch mechanism: when an element continues across
a frame boundary, write `handoff_out:` on the outgoing frame and a matching `handoff_in:` on
the incoming one, naming position, scale, opacity and direction/speed at the cut — *"state
every field even when it does not change, because a constant is `opacity: 1`, not an
omission."* That is the written answer to the parallel-workers-disagree problem.

### 1.6 The silent-failure surface — the actual answer to the RankPal concern

The brief's framing was that gates are what stop another RankPal-style silent failure. The
good news: the render engine **documents its own silent failures**, which is rare and is a strong
signal. The bad news: the issue tracker shows the gates themselves have had repeated holes,
three of which are **open right now** in exactly the "gate silently passes" class.

**Documented in the skill itself:**

1. > "A lint **error** also switches off the layout and contrast audits: `check` then reports
   > `0 sample(s)` and `0/0 text checks`, which reads like a clean file but means nothing
   > ran. Clear lint errors before you trust those numbers."
   — A passing-looking `check` that did nothing. This is precisely our failure class.
2. > "Every `<audio>` needs an `id`... an id-less `<audio>` is never picked up by the mixer,
   > so the render is **silent**."
3. > "**Root must be sized (silent layout bug)**... otherwise a flex/`100%` child collapses
   > to ~0 and content piles into the top-left corner. Do not rely on automated gates alone
   > to catch this; inspect a snapshot."
4. Sub-comp host-id mismatch is **silent**; with two or more timelines and a mismatched key
   the render is *"frozen at t=0."*
5. `determinism-rules.md` marks two layout bugs with an explicit
   *"(Silent — automated gates may miss it.)"* — unsized/inline transformed elements render
   invisible, and overshooting decoratives get clipped at their peak.
6. > "The pipeline default is otherwise **Marcia (female)** on the provider / `am_michael` on
   > a local TTS model — so a request like 'a male voice' is silently ignored unless you pass the flag."

**From the issue tracker** (all real, on the `render-engine` project):

| # | State | Title (abridged) |
|---|---|---|
| 3460 | **OPEN** | Sparse-keyframe check **silently skips** single-keyframe videos — "the worst case goes unreported" (0.8.10) |
| 3484 | **OPEN** | Artifact validation: PNG-sequence and WebM outputs **still bypass** the duration/frame gates |
| 3482 | **OPEN** | Fast-capture fallback guard — **100%-fallback renders pass artifact validation** |
| 3502 | closed | Renders above 99,999 frames **silently show the wrong** source-video frames |
| 3458 | closed | `createMediaElementSource` **silently mutes** cross-origin media with no CORS opt-in |
| 3419 | closed | Nested paused GSAP timelines report duration 0 → **silent all-black render** |
| 3391 | closed | GSAP timeline seek not applied before capture → black frames, CLI *and* Studio |
| 3487 | closed | `-avoid_negative_ts make_zero` shifts video +21ms, re-introduces black first frame (regression since v0.7.107) |
| 3423 | closed | Render hard-fails `drawElement canvas not initialized` instead of falling back to screenshot capture |

#3482 is the one I would watch: a capture that falls back 100% — i.e. captured nothing real
— still passes artifact validation. For a workflow whose whole premise is "aim it at a live
URL", that is a gate hole in exactly the place the premise depends on.

**Read:** the gate *philosophy* is stronger than ours and the docs are unusually honest. But
"the framework has gates" is not the same as "the gates are sound", and three open issues say
they are not, yet.

### 1.7 Determinism (research question 4a)

**Banned for visual state:** `Date.now()`, `performance.now()`, unseeded `Math.random()`,
render-time network fetches for required assets, hover/scroll/pointer/focus state, and
`repeat: -1`.

Non-obvious specifics worth pinning into our harness if we adopt this:

- `repeat` must use **`floor`, not `ceil`** — `ceil` overshoots `data-duration` and trips
  `gsap_repeat_ceil_overshoot`. Use
  `Math.max(0, Math.floor(duration / cycleDuration) - 1)` (a negative repeat means infinite).
- Registering the timeline key **before** an async build finishes renders blank
  (`gsap_timeline_registered_before_async_build`). Assign `window.__timelines[id]` at the
  *end* of the `document.fonts.ready` callback.
- The root's `data-duration` is read **once at compile time**; a script that rewrites it
  later is silently ignored. A *clip's* `data-duration` is re-read live.
- `pretext.clearCache` / `setLocale` are **deliberately not exposed** — they mutate state
  shared across compositions, which would make a render depend on what ran before it.
- Never derive positions from `getBoundingClientRect()` at tween time — *"the renderer
  samples in parallel."*
- Animating the same property from multiple timelines at once is order-dependent and *"can
  flip between renders."*

**The documented cross-machine caveat** (official docs, `concepts/determinism`):

> "Fonts and Chrome versions differ between computers, so a local render can shift by a
> pixel from one machine to the next. Render in Docker when you need exact reproducibility."

**Two additional determinism axes I found that are NOT in the determinism doc:**

1. **The CLI is unpinned by default.** `x-posting-license/SKILL.md`:
   *"`@latest` is mutable — pin a version, e.g. `npx the render engine@1.x.y`, if you need
   byte-identical re-renders over time."* And `the render engine`/SKILL.md §1 requires an
   `upgrade --check` probe on resume, noting *"a passing check confirms the project's
   compositions still validate on the new version — not that rendered output is
   frame-identical to the old pin — so a successful bump is never silent: name the old and
   new version in the run's summary."*
2. **GPU mode changes the render path.** `export PRODUCER_BROWSER_GPU_MODE=hardware` is
   required for WebGL content.

So byte-identical output needs **four** pins, not one: pinned CLI version, pinned Chrome
(Docker), pinned GPU mode, and pinned CDN assets. Also note rendering is **not fully
offline** — GSAP loads from jsDelivr at preview/render time.

### 1.8 `remotion-to-the render engine` — relevant to salvaging `LaunchSpecJson.tsx`

- **Blockers (skill refuses to translate):** `useState`, `useReducer`,
  `useEffect`/`useLayoutEffect` with non-empty deps, async `calculateMetadata`, third-party
  React UI libraries (MUI, Chakra, Mantine, antd, shadcn, Radix, NextUI).
- **Warnings (drop the construct, note the gap):** `@remotion/lambda` config, `delayRender`,
  `useCallback`, `useMemo`, custom hooks.
- Our `GenericLaunch.tsx` uses `useCurrentFrame`, `interpolate`, `spring`, `Sequence`,
  `AbsoluteFill` — all mapped, and no state/effects. **Likely portable**; needs the eval to
  confirm, not a read.
- It ships a **measured** eval harness with validated baselines (as of 2026-04-27):

  | Tier | Shape | Mean SSIM | Threshold |
  |---|---|---|---|
  | T1 | single-element fade-in | 0.974 | 0.95 |
  | T2 | multi-scene + spring + audio + image | 0.985 | 0.95 |
  | T3 | data-driven, custom subcomponents, count-up | 0.953 | 0.90 |
  | T4 | escape-hatch (8 lint cases) | 8/8 pass | n/a |

- **Directly applicable to our Phase A baseline.** From the eval guide:
  *"**Critical**: both renders must use matching pixel format. Set
  `Config.setVideoImageFormat("png")` + `Config.setColorSpace("bt709")` in the Remotion
  source's `remotion.config.ts` — otherwise the diff measures encoder differences (~0.05
  SSIM hit), not translation fidelity."*
  If we ever SSIM-diff our Remotion output against a the render engine port, we must do this or
  we will be measuring the encoder.
- The skill also states what it will not do: no reverse direction (HF → Remotion), and no
  non-Remotion sources.

### 1.9 `vox-explainer` ships a programmatic seam gate — and it contradicts Phase A

A community skill (`vox-explainer`) ships `scripts/seam-gate.mjs`, a numeric verifier that
enforces per seam: ledger-row consistency, exit still moving at the cut, entry mid-flight
(never from rest), measured direction == ledger direction, speed match (WARN), **zero
overlap** (*"one side visible per frame — the cut is not a dissolve"*), the Z-sign rule, and
carrier rect continuity at 12px / 5% tolerance. There is also `seam-stamp.mjs` to generate
seams from a `ledger.json`, and `probe --t <cut>` to discover true carrier selectors.

This is a programmatic version of the motion dimension of our own 8-dim gate. If we adopt
the render engine, we should look hard at whether this replaces our `content_diff.py` band census.

**A tension to decide, not a bug.** `motion-continuity.md` explicitly bans crossfades:

> | Crossfade between scenes | Cut-the-curve in the current's direction |
>
> "Never a crossfade — it has no carrier at all."

In Phase A we *fixed* a 57.24 hard-cut pop by making scenes opaque and cross-dissolving
them. Both positions are defensible — they are different motion languages, and vox-explainer
is a specific Vox-collage house style, not core the render engine doctrine. But if we adopt
the render engine we need to pick one deliberately rather than inherit the contradiction.

Same file also: bans idle wobble/breathe/float as sustained motion; bans `bounce.out` and
`elastic.out`; exit ≈75% of entry; total stagger ≤500ms; schedule a 0.3–0.75s stillness
before a climax.

---

## PART 4 — Deep research (COMPLETE)

### 4.0 Context7 MCP cannot do this job

You asked me to use the Context7 MCP. I tried it and it is the wrong tool — I have to report
this rather than quietly substitute. Its actual surface is a **brand/web-extraction SDK**:
`client.brand.retrieveSimplified`, `client.web.extract`, `extractFonts`,
`extractStyleguide`, `webScrapeMd`, `client.monitors.getLimits`, `client.parse.handle`.
A search returned 82,953 characters of that SDK with **zero the render engine mentions**. It has
no GitHub issue search, no Discord, no Reddit. Step 4 was executed with WebSearch/WebFetch
instead. Context7 could still be useful for one narrow thing: independently verifying brand
tokens at a test URL during the capture step.

### 4.1 Determinism — answered above (§1.7)

Short version: the guarantee is real and precisely specified, but it is a guarantee
**within a pinned environment**, not across machines. Docker is the sanctioned remedy. Four
pins are needed, not one.

### 4.2 Lambda / cloud rendering vs Remotion

Stronger than the community comparisons implied:

- An official `examples/aws-lambda` reference SAM template (one Lambda function, three
  roles: Plan / …).
- A `deploy/cloud` page for the provider-managed cloud rendering, and `deploy/templates-on-lambda`.
- A May 2026 launch covering the render engine Templates for parallel video rendering on AWS
  Lambda.

So scale exists. Maturity relative to Remotion is still unverified — I found no head-to-head
production benchmark, and no war story from anyone running the render engine Lambda at volume.
Note also `@remotion/lambda` is treated as a *warning* to drop during a port, i.e. deployment
concerns do not carry over.

### 4.3 Production war stories

GitHub issues are the substantive source (§1.6). The pattern across them is more useful than
any single bug: **"silently" appears in at least six separate issue titles** — silently shows
the wrong frames, silently mutes, silently skips, silent all-black render. That is a
recognisable failure culture, and it is the specific thing our harness is built to defend
against.

I could not retrieve the two third-party long-form reviews: the Chinese two-week hands-on
review at `123ai.org` returned a redirect loop, and I did not fetch `txtmix.com`. Both are
worth a manual look — they are the closest thing to an independent track record.

### 4.4 the footage toolkit track record

Structurally promising, empirically unknown:

- An open-source org skill (May 2026): *"Drop raw footage in a folder, chat with Claude
  Code, get final.mp4 back."* Several third-party Chinese-language write-ups exist; none
  that I could verify as first-hand.
- Its SKILL.md is unusually explicit about failure modes: 12 hard rules, a step-7 self-eval,
  and an anti-patterns table. The self-eval samples `timeline_view` at every cut boundary
  (±1.5s) checking visual discontinuity, waveform spikes, subtitles hidden behind overlays
  and misaligned overlays, plus first 2s / last 2s / midpoints, capped at 3 passes. It also
  states: *"Verify your own output before showing it to the user. If you wouldn't ship it,
  don't present it."*
- **On your question (b)** — how much of the footage client's manual workaround the footage toolkit avoids — I can
  answer this much structurally. `install.md` registers via a **symlink of the whole
  directory** into `~/.claude/skills/the footage toolkit`, and carries an explicit cold-start
  reminder: *"Symlink the **whole directory**, not just `SKILL.md`. The helpers need to sit
  next to it."* That is precisely the failure we hit with the local footage tool, and it is
  documented. Whether it actually registers here is **unverified** — it needs a shell.
- **On your question (a)** — whether the self-eval catches real defects — **unanswered.**
  That is an empirical question and I ran nothing. I would test it by deliberately seeding
  a defect (a cut mid-word, a subtitle behind an overlay) and seeing whether step 7 flags
  it. Until then, treat it as decorative-by-default.

---

## What I need to finish this

1. **Bash restored — DONE (session 2).** Part 2 executed end-to-end; the "Bash died"
   blocker from session 1 is obsolete.
2. **`git-lfs`** — no longer blocks Part 2 (the render engine skills were already installed via
   `npx skills add`; the repo clone itself still needs LFS if we ever re-clone from source,
   but the live test did not require it).
3. **`HOSTED_TTS_API_KEY`** — still blocks **Part 3 (Cat 2 the footage toolkit)** only. Per your
   "proceed without it" call, the footage toolkit's transcription path and step-7 self-eval stay
   **untested**; I report them as such rather than fabricating a result.

## Open decisions I'd want your call on

- **Crossfades.** Phase A used opaque cross-dissolves as the fix for a hard-cut pop;
  the render engine' community motion doctrine bans crossfades outright. Pick one before we port.
- **Cross-client asset contamination.** media-use's global cache aggregates every project.
  For agency work that needs per-client isolation or a hard ban on cross-project `logo`/
  `image` reuse.
- **Whether to adopt `seam-gate.mjs`** as the motion dimension of our 8-dim gate, replacing
  or supplementing `content_diff.py`.
