# Generic launch template — Category 3 (pure product motion)

Use for: launch / explainer videos that can be **drawn** — UI, text, shapes,
motion graphics. No live footage (that is Category 2, see `the footage client-editor.md`).

**You author one small JSON file. You do not write TSX, `render.json`, or a
scene graph.** The composition component is already written and is
product-agnostic; the brief supplies every product-specific value.

> This document is self-contained. An agent with no other context should be able
> to take a product brief and produce a finished MP4 from this page alone.

---

## 1. What it is

A Remotion project whose single composition is driven by `brief.json`.

- **Engine location:** `./engine/remotion-generic`
- **Composition id:** `LaunchTemplate`
- **Entry:** `src/index.ts` → `src/Root.tsx`
- **Component:** `src/GenericLaunch.tsx` (props-driven, zero product hardcoding)
- **Output:** `out/launch.mp4`

Three scenes, always: **title → feature(s) → CTA.** Scene lengths are fractions
of the total runtime, so any `durationInFrames` works without retuning.

**No the launch-spec format, no `render.json`, no `bundledJs`, no scene graph.** See §7 for
why that path is closed.

## 2. Setup

```bash
cd ./engine/remotion-generic
npm install          # remotion, @remotion/cli, react, react-dom, typescript
```

`npm install` downloads ~184 packages and, on first render, Chrome Headless
Shell (~150 MB). Both are one-time.

## 3. The brief — `brief.json` (this is your only authoring surface)

Field names mirror the the launch-spec format document schema (`name`, `accentColor`,
`backgroundColor`, `durationInFrames`) because that shape is already validated
in production.

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | string | **yes** | — | Product name. Rendered as the title. |
| `accentColor` | string | **yes** | — | Brand colour, `#rrggbb`. Drives title, bullets, rule, CTA pill. |
| `backgroundColor` | string | **yes** | — | Canvas background, `#rrggbb`. |
| `durationInFrames` | number | **yes** | — | Total length in frames. `300` @ 30fps = 10s. |
| `features` | string[] | **yes** | — | Feature list. One string per feature. |
| `tagline` | string | no | *none* | One line under the title. |
| `ctaText` | string | no | `Get <name>` | CTA button label. |
| `ctaUrl` | string | no | *none* | Small line under the CTA (e.g. `plink.app`). |
| `screenshotUrl` | string \| null | no | `null` | Filename **inside `public/`**. See §4. |
| `fps` | number | no | `30` | |
| `width` | number | no | `1920` | |
| `height` | number | no | `1080` | |

### Minimal valid brief

```json
{
  "name": "Harbor",
  "accentColor": "#0f766e",
  "backgroundColor": "#ffffff",
  "durationInFrames": 300,
  "features": [
    "Track shipments in one timeline",
    "Alert me before anything slips",
    "Share a live status page"
  ]
}
```

That is the whole authoring step. `tagline`, `ctaText`, `ctaUrl`, and
`screenshotUrl` are all optional — `ctaText` derives from `name` if omitted.

### Worked example (Harbor, with every optional field)

```json
{
  "name": "Harbor",
  "tagline": "Freight tracking your whole team can actually follow",
  "accentColor": "#0f766e",
  "backgroundColor": "#ffffff",
  "durationInFrames": 360,
  "fps": 30,
  "width": 1920,
  "height": 1080,
  "features": [
    "Track shipments in one timeline",
    "Alert me before anything slips",
    "Share a live status page"
  ],
  "screenshotUrl": "harbor.png",
  "ctaText": "Start free",
  "ctaUrl": "harbor.app"
}
```

## 4. Adding a screenshot (optional)

1. Put the image in `public/` — e.g. `public/harbor.png`.
2. Set `"screenshotUrl": "harbor.png"` (filename only, **not** a path).

It renders in the feature scene beside the list. Omit it (or `null`) and the
feature list centres on its own. Both layouts are supported.

## 5. Commands

```bash
cd ./engine/remotion-generic

export PATH="$PATH:your Homebrew bin"                                        # APPEND
export PATH="$PATH:<agent-runtime>/binaries/node/versions/22.22.2/bin"
unset NODE_OPTIONS

npm run render                    # -> out/launch.mp4
npm run still -- --frame=20       # single PNG, cheap check before a full render
npm run preview                   # interactive
```

## 6. Environment gotchas (all hit for real)

1. **Append PATH, never prepend.** Prepending puts `your Homebrew bin` first and
   flips Node to v26, which changes Remotion's runtime cache key and dies with
   `runtime cache is absent`. Always `export PATH="$PATH:..."`.
2. **`unset NODE_OPTIONS` before `render` / `still`.** An injected Node `fs` shim
   throws `EEXIST` on `mkdir` otherwise.
3. **Use Node v22.** Check with `node --version` → `v22.x`.
4. **`out/` is overwritten** on each render (`Config.setOverwriteOutput(true)`).

## 7. Why not the launch-spec format / `render.json`

Investigated 2026-09-01. the launch-spec format (`the launch-spec service`) is a **hosted, login-gated
SaaS**. `render.json` is a *compiled export* of their cloud agent — scene content
lives in `clip.props.browserAgentOutput.bundledJs`, which is TSX their LLM wrote.
There is no public API (`/docs` is a 404, the editor is auth-walled), and even if
there were, calling it would upload the brief to a third party and break the
harness's key-free, fully-local property. **That path is closed. Do not attempt
to hand-author `render.json`** — it is a machine-generated scene graph, not a
template.

## 8. Verification — prove it, don't eyeball it

"I looked at it" is not evidence. Use structural, pixel, or media evidence.

### Media probe

```bash
your Homebrew bin/ffprobe -v error -show_entries format=duration,size \
  -show_entries stream=codec_name,width,height,nb_frames \
  -of default=noprint_wrappers=1 out/launch.mp4
```

### Stills + pixel sampling

Render stills at a frame inside each scene, then count pixels:

```bash
cd ./engine/remotion-generic
export PATH="$PATH:your Homebrew bin"
export PATH="$PATH:<agent-runtime>/binaries/node/versions/22.22.2/bin"
unset NODE_OPTIONS
npm run still -- --frame=20  # single PNG, adjust per scene
```

```bash
<agent-runtime>/binaries/python/envs/default/bin/python - <<'PY'
from PIL import Image
im = Image.open("out/launch-frame.png").convert("RGB")
px = list(im.getdata()); n = len(px)
nonwhite = sum(1 for r,g,b in px if not (r>250 and g>250 and b>250))
def near(c, tol=40):
    r0,g0,b0 = c
    return sum(1 for r,g,b in px if abs(r-r0)<tol and abs(g-g0)<tol and abs(b-b0)<tol)
print("size", im.size)
print(f"nonwhite={nonwhite} ({100*nonwhite/n:.2f}%)")
print("accent px =", near((15,118,110)))   # pass your brief's accentColor as RGB
PY
```

Convert a hex accent to RGB: `#0f766e` → `(15, 118, 110)`.

### OCR — prove what the frame actually says

```bash
your Homebrew bin/ffmpeg -y -i out/launch.mp4 -vf "select=eq(n\,20)" -frames:v 1 /tmp/f20.png
<agent-runtime>/binaries/python/envs/default/bin/python \
  ./review/ocr_frames.py /tmp/f20.png --show-all
```

`ocr_frames.py <frames> --grep term` exits **1** if the term is found — usable as
a gate (e.g. confirm the product name is present; confirm a foreign product's
name is **absent**).

## 9. Review gate

Before calling it done, score all **8 dimensions** in `review/criteria.md`:
`hook_and_value_clarity`, `product_capability_accuracy`,
`brand_consistency_and_visual_craft`, `motion_continuity_and_pacing`,
`narration_quality_and_audio`, `subtitle_readability_and_optional_playback`,
`launch_readiness_and_call_to_action`, `brief_length_match`.

- Every applicable dimension must independently be **≥ 4**. An average cannot
  compensate.
- `n/a` is allowed **only** when the brief did not ask for it — and needs a
  written reason (e.g. no narration was requested → `narration_quality_and_audio`
  is `n/a`).
- Emit the JSON score block from `review/criteria.md` §5.
- Present **the artifact and the numbers together**, not a description.

## 10. What the template actually produces

Knowing the shape of the output helps you write a brief that fits.

**Scene 1 — title (30% of runtime).** Eyebrow `INTRODUCING` (muted grey, 30px,
letter-spaced) → product name (150px, accent, 800 weight, spring-pop) →
accent rule (320px → 0px grow) → tagline (44px, fades + slides up). On a
white background the title scene lands at ~0.9% accent coverage from the
name + rule alone.

**Scene 2 — feature (40% of runtime).** Heading `What <name> does` (60px) +
accent rule. Below: one row per feature, each starting with a **numbered
accent chip** (56px circle, 1/2/3, white digit) — not a plain dot. The
feature list is the longest scene and the brand presence is the thinnest
of the three (~0.3–0.4% accent by pixel count). With a `screenshotUrl`,
the list is half-width and the screenshot fills the other half. Without,
the list is centred in a 1200px reading column.

**Scene 3 — CTA (30% of runtime).** Large accent pill (`Get <name>` by
default) → optional `ctaUrl` line below → product name as a small footer.
CTA scene lands at ~1.6% accent coverage from the pill.

**Transitions.** 12-frame (0.40s) cross-dissolve between every pair of
adjacent scenes. The outgoing scene is held past its solo end so the
incoming one has a fully-opaque frame to dissolve into — measured peak
inter-frame motion is 17.5 (content-restricted), well inside the
"2–25 gradual" band that `review/criteria.md` defines as good. No hard
cuts.

**Why no transparent overlays.** The composition root and every scene
`Frame` is opaque (`backgroundColor` filled). The motion gate requires
this — transparent scenes cause the outgoing content to vanish the moment
its `Sequence` ends, producing a near-hard-cut pop (~57 content-diff in
the prior version). The fix is structural, not a tuning knob.

**Defaults you can rely on.** `fps: 30`, `width: 1920`, `height: 1080`,
`ctaText: "Get <name>"`. Silent cut — there *is* an AAC stereo stream in the
output (Remotion's default container puts one there) but it measures −91.0 dB
(digital silence) end-to-end. It is not meant to be heard.

**`brief.json` path.** The file lives at
`./engine/remotion-generic/brief.json` —
directly in the engine root, sibling to `package.json`. The doc never
stated the path explicitly and a doc-only test had to guess it; the path
is now stated here.

