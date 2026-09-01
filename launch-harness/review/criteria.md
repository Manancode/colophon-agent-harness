# Review gate — 8 dimensions, agent-applied

**Who runs this:** you, the agent, against your own output, *before* you tell the
human you're done. There is no server here and no second model. You score, you
revise, you re-score.

**Bar:** every dimension independently ≥ **4 / 5**. An average cannot compensate
for a weak dimension. A 5,5,5,5,5,5,2 is a **fail**.

**Retry budget: 3 attempts.** Attempt 1 = your first honest pass. If any
dimension is < 4, revise *that dimension specifically* and re-render. After
attempt 3, **stop and flag the human** with the blocking dimension, what you
tried, and what you need from them. Do not loop past 3.

---

## 0. The honesty rule (read this first)

**Do not claim you looked at an image.** Most agents running this skill cannot
actually see a PNG. Scoring `brand_consistency_and_visual_craft: 5` because
"the frame looks clean" is fabrication, and it is the single easiest way to
make this whole gate worthless.

Every score below must be backed by one of three **evidence channels**, and you
must record which one you used:

| Channel | How | Proves |
|---|---|---|
| **S / Structural** | Read the composition source (`render.json`, or the `.tsx`) | What text, timing, colors, and transitions were *declared* |
| **P / Pixel** | Sample the rendered PNG with PIL — see §3 | What actually *rendered* (color present, not black, not blank) |
| **M / Media** | `ffprobe -v error -show_streams -show_format` | Duration, codec, resolution, stream count |

A dimension you can only back with "I looked at it" gets **no score** — it gets
`needs_visual_review` and goes to the human.

**N/A is not an escape hatch.** Mark a dimension `n/a` only when the *brief did
not ask for it*. If the brief asked for narration and there is no audio, that
is a **1**, not an `n/a`. Every `n/a` requires a written `na_reason`.

---

## 1. The eight dimensions

Score each 1–5. Anchors: **5** = no notes, ship it · **4** = minor, acceptable ·
**3** = noticeable weakness · **2** = clearly below bar · **1** = broken or absent.

---

### 1. `hook_and_value_clarity`
The opening communicates **product name + audience + one value proposition** in
plain language, within the first 3 seconds.

- **Evidence S:** read clip at `startFrame: 0`. Does its text/UI contain the
  product name and a benefit a stranger would understand?
- **Evidence P:** sample a frame at t≈1.5s and t≈2.5s. Non-background pixel
  coverage must be > 2% (i.e. something is actually on screen, not a hold on
  empty canvas).

*Worked example (RankPal `render.json`):* clip at frame 0 is `TextType`,
`text: "Introducing RankPal\nA new way to grow on the App Store"`. Name ✓,
value prop ✓, plain language ✓. At 30fps that copy is typed with
`typingSpeed: 1` / `initialDelay: 15` — check the full second line is complete
by frame 90 (3.0s) or this drops to 3.

---

### 2. `product_capability_accuracy`
Every visible title, number, and claim is grounded in the brief. **No invented
or extrapolated features.**

- **Evidence S:** enumerate every string that renders (clip `text`, `props.url`,
  `chatHistory[].content` shown on screen). For each: is it in the brief?
- **Blocker:** any capability not in the brief → automatic **1**, full stop.

*Worked example:* RankPal `render.json` layers 3–5 render
`a third-party demo URL — a **third-party product**, not
RankPal. Unless the brief put that in scope, this is a capability/brand accuracy
blocker even though it renders fine. This is exactly the class of defect that a
"the video looks smooth" glance misses entirely.

---

### 3. `brand_consistency_and_visual_craft`
Brand background, accent, and foreground applied consistently; typography
restrained and readable; canvas is an **unaltered opaque brand background**.

- **Evidence S:** collect declared colors. Document root `backgroundColor`,
  `accentColor`; per-clip `props.color`, `props.bgColor`, `props.accentColor`.
  Count distinct accent values.
- **Evidence P:** sample rendered frames, extract dominant non-background color,
  compare to declared hex.

**Blockers (any one → ≤ 2):** transparent / tinted / gradient / image scene
root; opacity, filter, mask, blend, or clip on the primary root.

*Worked example:* document declares `backgroundColor: "white"`,
`accentColor: "#0ea5e9"` = RGB `(14, 165, 233)`. So: root must sample
`(255,255,255)`; the accent, where used, must sample ≈ `(14,165,233)`. Note
layer 5 overrides `accentColor: "#8b5cf6"` — a second accent in a
four-scene video. Deduct at least 1 unless the brief sanctions two accents.

---

### 4. `motion_continuity_and_pacing`
Scene-to-scene change is continuous (crossfade, push, or hold). Pacing supports
comprehension. **No abrupt hard cuts.**

- **Evidence S:** for each clip read `transitionIn`, `transitionOut`, `motion`,
  and `startFrame` / `durationInFrames`. A clip with **neither** transition nor
  motion, abutting its neighbour, is a hard cut.
- **Evidence P:** sample frames either side of each boundary. Compute mean
  absolute pixel difference. A hard cut → large jump; crossfade → gradual.

**A project with no transitions at all scores at most 3.**

*Worked example:* `durationInFrames: 670` @ `fps: 30` = **22.33s** — matches a
"20-second" brief within tolerance. Six clips over 670 frames ≈ 111 frames
(3.7s) each, which is tight for readable copy; verify no clip's text is still
mid-animation when the next clip starts.

---

### 5. `narration_quality_and_audio`
Spoken text intelligible, natural, complete, and aligned to each scene's timing
budget.

- **Evidence S:** `document.audioTracks` length; `audioOptions.voiceovers`.
  Zero audio tracks and a brief that asked for narration → **1**, not `n/a`.
- **Evidence M:** `ffprobe` — is there an audio stream? Duration ≥ video?
- **Evidence P:** waveform peak check if a WAV exists.

**N/A only if** the brief explicitly asked for a silent / music-only cut.
Record `na_reason`.

---

### 6. `subtitle_readability_and_optional_playback`
Captions accurate and readable **when enabled**, and the composition works with
them **disabled** (default off, toggle present).

- **Evidence S:** is there a subtitle artifact (`.srt` / `.vtt`) bound to the
  composition? Is it default-off with a toggle?
- **Evidence P:** sample a frame with captions on — is the caption area
  legible (contrast ratio, not overlapping primary content)?

**Forced-always-on captions is a blocker.** Missing captions when the brief
asked for them is a blocker.

---

### 7. `launch_readiness_and_call_to_action`
The closing scene names the concrete next step (install / visit / sign up) and
the audience knows what to do.

- **Evidence S:** read the **last** clip by `startFrame`. Does it name an action?
- **Evidence P:** sample the final 2 seconds. Non-blank, and the CTA surface is
  on screen long enough to read (≥ 1.5s).

*Worked example:* read the ending with `ocr_frames.py`; do not grep the source
for a URL you guessed. Grepping `rankpal.com` finds nothing while the rendered
frame actually reads `rankpal.app` — a wrong guess here under-scores a CTA that
passes.

---

### 8. `brief_length_match`
The delivered runtime matches the length the brief asked for.

- **Evidence S:** read the composition's declared duration source (a document's
  `durationInFrames`, or the composition's own duration constant). Compare it
  to the brief, **and to what the code actually uses**.
- **Evidence M:** `ffprobe` duration. Tolerance ±10% of the requested length.

**Blocker — source/render drift.** If the composition source declares one
duration and the render produces another, treat the **drift as the bug**, not
the longer cut as a newly intended length. The spec that was validated
end-to-end wins, unless the human explicitly confirms the new length.

*Worked example:* a "20-second" brief rendering 70.03s / 2101 frames because the
TSX hardcodes a 7-scene narrative while `render.json` declares
`durationInFrames: 670`. That is a **1** and a blocker. Fixed by trimming to
670 frames = 22.33s.

---

## 2. Global blockers (any one → `verdict: "fail"` regardless of scores)

- Invented or unbriefed capability.
- Unsafe / unlicensed / third-party asset presented as the product's own.
- Off-brand or illegible canvas.
- Non-seekable or frame-clock-dependent motion (relies on wall-clock, not the
  render clock → breaks scrubbing and re-renders).
- Missing or forced subtitles.
- Inaudible or truncated narration.
- Missing or unclear call to action.
- Transparent / tinted / gradient / image composition or scene root.
- Opacity, filter, mask, blend, or clip applied to the primary root.

---

## 3. Pixel sampling recipe (the P channel)

Use the bundled tool — it covers every P-channel check in one pass:

```bash
PY=<agent-runtime>/binaries/python/versions/3.13.12/bin/python3
$PY ./review/sample_frames.py \
    out/review-f45.png out/review-f90.png out/review-f335.png out/review-f640.png \
    --color accent=#0ea5e9 --color offbrand=#8b5cf6 \
    --diff
```

It prints, per frame: dominant colors with counts, center pixel, non-white %,
near-black %, and a count for each `--color` you name. `--diff` adds
frame-to-frame mean absolute difference for dimension 4:

| mean abs diff | reading |
|---|---|
| `< 2` | static hold |
| `2 – 25` | gradual (crossfade / push) — good |
| `> 60` | near-total change in one step = **hard cut** |

Use it for, at minimum: **one frame per scene**, plus **both sides of every
scene boundary**.

If the tool is unavailable, the equivalent inline check is:

```python
from PIL import Image
from collections import Counter
im = Image.open("/abs/path/frame.png").convert("RGB")
c = Counter(im.getdata())
for col, n in c.most_common(5):
    print(col, n, f"{100*n/(im.size[0]*im.size[1]):.2f}%")
target = (14, 165, 233)                       # #0ea5e9
hit = sum(n for col, n in c.items()
          if all(abs(a-b) <= 12 for a, b in zip(col, target)))
print("accent px:", hit)
```

---

## 4. Getting frames to sample

**Remotion path:**
```bash
cd your product video project
export PATH="$PATH:your Homebrew bin"      # APPEND — see tools/remotion-pipeline.md
npx remotion still src/index.ts LaunchSpecJson out/rev-<n>-f<frame>.png --frame=<frame>
```
Sample at least: frame 45 (1.5s), frame 90 (3s), the midpoint, and the last
frame minus 30.

**the footage client path:**
```bash
the footage client capture <composition-id> -t <seconds> -S -o /tmp/review
```
Capture at `-t 1` or later, never `-t 0` (fade-in is still un-composited at 0).

---

## 5. Required output

Emit this block **before** you present the artifact. Scores must be integers
1–5 or `null` (only with `needs_visual_review`). No booleans, no NaN, no
out-of-range values.

```json
{
  "attempt": 1,
  "route": "category-3-remotion | category-2-the footage client",
  "artifact": "/abs/path/to/output.mp4",
  "frames_reviewed": ["/abs/path/frame-a.png"],
  "dimension_scores": {
    "hook_and_value_clarity":               null,
    "product_capability_accuracy":          null,
    "brand_consistency_and_visual_craft":   null,
    "motion_continuity_and_pacing":         null,
    "narration_quality_and_audio":          null,
    "subtitle_readability_and_optional_playback": null,
    "launch_readiness_and_call_to_action":  null,
    "brief_length_match":                   null
  },
  "evidence": {
    "hook_and_value_clarity": "S: clip@frame0 text=... | P: 4.1% non-bg coverage @f45"
  },
  "na_dimensions": { "narration_quality_and_audio": "brief requested silent cut" },
  "blockers": [],
  "localized_repairs": ["layer 5: accentColor #8b5cf6 -> #0ea5e9"],
  "verdict": "pass | fail | needs_visual_review"
}
```

**Verdict rules**
- `pass` — every *applicable* dimension ≥ 4, no blockers.
- `fail` — any applicable dimension ≤ 3, or any blocker. Include
  `localized_repairs` naming the specific scene/clip/prop to change.
- `needs_visual_review` — a dimension genuinely cannot be scored without human
  eyes (you have no S/P/M evidence for it). List which.

**Never** present a video as done with a `fail` verdict, and never present it
with scores you can't attach evidence to.
