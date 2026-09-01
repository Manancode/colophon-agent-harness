# Remotion/JSON pipeline — Category 3 (pure product motion)

Use for: UI walkthroughs, abstract product animation, motion-graphics
explainers — everything is drawn, no live footage is cut.

Location: `your product video project`

## What it is

A Remotion project whose composition is driven by a the launch-spec format scene-graph export
(`render.json`). `npm run extract` turns that JSON into React scene modules under
`src/generated/`, and Remotion renders them to MP4.

**Key-free and fully local.** Dependencies are only `remotion`, `@remotion/cli`,
`react`, `react-dom` (+ `typescript`). No `fetch`, no `process.env`, no API
client anywhere in `src/`. Nothing leaves the machine.

## Commands (run from the package dir)

```bash
cd your product video project

npm run extract   # render.json -> src/generated/ (scene-*.js, scene-manifest.json,
                  #                launchspec-document.json, scene-registry.ts)
npm run preview   # extract + remotion preview src/index.ts        (interactive)
npm run render    # extract + remotion render src/index.ts LaunchSpecJson \
                  #                  out/launchspec-json.mp4 --codec=h264 --crf=18
npm run still     # extract + remotion still src/index.ts LaunchSpecJson \
                  #                  out/launchspec-json-frame.png --frame=150
```

- Composition id: **`LaunchSpecJson`**
- Entry: **`src/index.ts`** → `src/Root.tsx` registers the composition
- Output: **`out/launchspec-json.mp4`**
- Canvas size / fps / duration come from `render.json`
  (`document.fps`, `document.width`, `document.height`)

## Shape of the input

`render.json` (785 KB, minified single line) is the the launch-spec format export. Variants
`render2.json` … `render9.json` sit alongside it. The extract script reads
whichever file is at `render.json`, pulls each clip's embedded
`browserAgentOutput.bundledJs` out into a `scene-<layer>-<clip>.js` module, and
writes the manifest + registry. Clips with no bundled JS are skipped.

Verified 2026-09-01: `npm run extract` → `Extracted 4 embedded the launch-spec format scenes`.

## Gotchas (all hit for real)

1. **`ffmpeg` is not on the default PATH** and Remotion needs it to encode.
   Fix with `export PATH="$PATH:your Homebrew bin"` — **append, do not prepend.**
   Prepending puts node v26 first, which changes Remotion's runtime cache key
   (node major is part of it) and produces `runtime cache is absent`.
2. **Fixed 2026-09-01 — extract path bug.**
   `scripts/extract-launchspec-scenes.mjs` used `path.resolve('..')`, so it looked
   for `render.json` one directory *above* the package and died with
   `ENOENT: .../RankPal/render.json`. The file actually lives *next to*
   `package.json`. Changed to `path.resolve('.')`. If `npm run extract` ever
   ENOENTs again on a `render.json` path, this is why.
3. **`src/generated/` is regenerated on every extract** — never hand-edit it.
   Author changes go into `render.json` (or a bespoke TSX composition).

## Verification

- `npm run still` renders a single frame PNG — use it for a cheap visual check
  before committing to a full render.
- Probe the result:
  ```bash
  export PATH="$PATH:your Homebrew bin"
  ffprobe -v error -show_entries format=duration,size \
          -show_entries stream=codec_name,width,height \
          -of default=noprint_wrappers=1 out/launchspec-json.mp4
  ```
- Do **not** try to view a PNG directly; sample its pixels programmatically
  instead (see `tools/the footage client-editor.md` for the pixel-sampling recipe, which works
  for any PNG).
