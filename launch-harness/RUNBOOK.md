# Runbook — finishing the end-to-end harness test

**Status at time of writing:** the harness is built (all 5 files done), but the
final render could not be executed: the shell in this session is dead. Every
command returns exit code 127 with empty stdout and stderr — including `echo`.
This reproduces in a fresh subagent shell too, so it is environment-wide, not a
bad command. Nothing was fabricated to paper over it.

Everything below is copy-paste ready.

---

## Step 0 — Routing (already resolved, no shell needed)

Test request: **"make me a 20-second launch video for RankPal"**

Run it through the decision tree in `SKILL.md` §0.2:

1. Does it reference an existing video/audio file the user supplied? **No.**
2. Does it ask for narration, voiceover, or "cut to" language? **No.**
3. Can the whole thing be drawn (UI, text, shapes, motion graphics)? **Yes** —
   RankPal is a macOS app; a launch video is UI + kinetic text.

→ **CATEGORY 3 → Remotion.** Deterministic, not a judgement call. No clarifying
question needed, because no Category 2 trigger fired.

---

## Step 1 — Render

```bash
cd your product video project

# APPEND. Do NOT prepend — prepending puts your Homebrew bin first, which
# flips Node to v26 and Remotion dies with "runtime cache is absent".
export PATH="$PATH:your Homebrew bin"
export PATH="$PATH:<agent-runtime>/binaries/node/versions/22.22.2/bin"

node --version          # must print v22.x
npm run extract         # expect: Extracted 4 embedded the launch-spec format scenes
npm run render          # first run downloads Chrome Headless Shell (~150MB)
```

Expected: `out/launchspec-json.mp4`.

> Note: an older `out/launchspec-json.mp4` from Jun 20 already exists. Re-render
> anyway — the test is whether *this harness run* produces the artifact.

If `npx remotion` isn't found, call the CLI directly:
```
your product video project/node_modules/@remotion/cli/remotion-cli.js render src/index.ts LaunchSpecJson out/launchspec-json.mp4 --codec=h264 --crf=18
```

## Step 2 — Review stills

```bash
cd your product video project
export PATH="$PATH:your Homebrew bin"
export PATH="$PATH:<agent-runtime>/binaries/node/versions/22.22.2/bin"

for f in 45 90 335 640; do
  npx remotion still src/index.ts LaunchSpecJson out/review-f$f.png --frame=$f
done
```

## Step 3 — Media probe

```bash
your Homebrew bin/ffprobe -v error -show_streams -show_format \
  -of default=noprint_wrappers=1 \
  your product video project/out/launchspec-json.mp4
```
Record: duration, width, height, codec, frame count, audio stream present?
(Expect **no** audio — `document.audioTracks` is empty in `render.json`.)

## Step 4 — Pixel sample (the numbers)

```bash
<agent-runtime>/binaries/python/versions/3.13.12/bin/python3 \
  ./review/sample_frames.py \
  out/review-f45.png out/review-f90.png out/review-f335.png out/review-f640.png \
  --color accent=#0ea5e9 --color offbrand=#8b5cf6 \
  --diff
```

## Step 5 — Score

Fill `review/criteria.md` §5 from the output above. **Do not score a dimension
you have no evidence for** — that one goes to `needs_visual_review`.

Known ground truth from `render.json` (use it for dimension 2 and 3):

- 670 frames @ 30fps = **22.33s** (matches "20-second" brief)
- `backgroundColor: white`, `accentColor: #0ea5e9` = `(14,165,233)`
- Clip @ frame 0: `TextType` — "Introducing RankPal / A new way to grow on the
  App Store"
- **Layers 3, 4, 5 render `a third-party demo URL —
  a third-party product, not RankPal. Dimension 2 risk.
- **Layer 5 overrides `accentColor: #8b5cf6`** — a second accent. Dimension 3
  risk, worth at least −1 unless the brief sanctions it.
- **Layer 5 is the last clip and has no CTA text.** Dimension 7 risk.

---

## Two findings that contradict "no new code needed"

Both surfaced while building. Neither is a doc problem.

**1. `npm run extract` was genuinely broken — I fixed it.**
`scripts/extract-launchspec-scenes.mjs` resolved `render.json` with
`path.resolve('..')`, i.e. one directory *above* the package, so it looked for
`~/rankpal/RankPal/render.json` (doesn't exist) and threw ENOENT.
Changed to `path.resolve('.')`. Verified: `Extracted 4 embedded the launch-spec format scenes`.

**2. `node_modules` was effectively empty — I had to install.**
Only 3 stray packages (`@mediabunny`, `human-signals`, `jest-worker`) were
present; `@remotion/cli` was missing entirely, so `remotion render` failed with
`command not found`. Ran `npm install` → 184 packages, `@remotion/cli` 4.0.481.
The Remotion path was **not** runnable as-found.

Note: during that install, a safe-delete guard blocked npm's cleanup of
`@emnapi/wasi-threads` (`SAFE_DELETE_BULK_CONFIRM_REQUIRED`, 63 items over a
threshold of 50). That is the most likely trigger for the shell dying. It is
cosmetic to the install, but worth knowing if the shell dies again after a
large `npm install`.

Also outstanding: `npm audit` reports 3 high severity vulnerabilities in the
fresh tree. Not triaged.
