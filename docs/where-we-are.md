# Where we are

Blunt status. Not a plan — [roadmap.md](roadmap.md) is the plan. This is what is
actually true right now, including the parts that are uncomfortable.

Last revised 2026-08-30.

---

## What is built

31 commits, all on 2026-08-30. Roughly 11,400 lines across `colophon/`, 24 test
files, **446 tests passing**.

| Layer | State |
|---|---|
| Spec schema, clock, treatments | done |
| Fourteen deterministic QA gates | done |
| Closed-world taxonomy, fails closed | done |
| Contact sheet + independent review | done |
| Bounded repair loop (mechanical vs LLM routing) | done |
| MCP tool server (seven tools over HTTP) | done |
| TrueForge wiring, verified with a real transcript | done |
| Exemplar library | **not started** |
| Renderer exercised end to end | **unverified — see below** |
| Qodo review trail | **pending; app not installed** |
| Demo video | **not recorded** |

---

## The renderer: what changed, and what is still open

The write-up says "rendering is not exercised in this environment." That was
true but misleading, and the honest version is more useful.

`colophon doctor` resolves **everything**:

```
ffmpeg     8.1       /opt/homebrew/Cellar/ffmpeg/8.1_1/bin/ffmpeg
ffprobe    8.1       /opt/homebrew/Cellar/ffprobe/8.1/bin/ffprobe
node       26.5.0    /opt/homebrew/Cellar/node/26.5.0/bin/node
npm        11.17.0   /opt/homebrew/lib/node_modules/npm/bin/npm-cli.js
cache_key  8dbb183a788cc297
```

The tools were never the blocker. What was missing was `node_modules` in
`colophon/renderers/hyperframes/runtime/` — a directory whose `package.json`
depends on `hyperframes@0.7.86` and requires node `>=22`. Node 26 satisfies it.

`npm install` there now adds **136 packages**, and `hyperframes@0.7.86` is
present on disk.

**Verified working.** `npm install` added **136 packages** including
`hyperframes@0.7.86`; `esbuild@0.25.12` runs despite its skipped postinstall
(the `@esbuild/darwin-arm64` platform binary is present). `colophon deliver
runs/cadence-01 --review` renders a **1920×1080, 30 fps, 43.67 s** video and
**all 14 gates pass** end to end (verified attempt 05). The ten render-dependent
gates have now executed against a real video — the single biggest gap is closed.

---

## Honest weaknesses

Stated plainly, because a judge will find them anyway.

1. **All 31 commits are one day old, and the first 25 were direct pushes to
   `main`.** No review trail exists for them and none can be retro-fitted. This
   is disclosed in the README rather than hidden.
2. **The central bet is untested.** "A closed vocabulary makes taste
   measurable" is the thesis. There is no exemplar library and the grammar is 6
   roles, 12 treatments, **3 motions**. Nobody has human-rated a single output.
   Roadmap step 3 (generate 20, score the failures) has not run.
3. **Best UI is a stretch.** This is a CLI that reads JSON and writes JSON. The
   contact sheet is the only visual artifact. Of the three hackathon tracks,
   *Best Use of TrueForge* and *Best Code Quality* are the real ones.
4. **Qodo has not reviewed anything.** The app is not installed. Every claim in
   `## Qodo Code Review Evidence` is currently a claim about the future.

---

## Punch list, in the order it matters

1. **Run one real render — DONE.** Verified: `colophon deliver runs/cadence-01
   --review` renders a 1920×1080 30 fps video and **all 14 gates pass** (attempt
   05). The ten render-dependent gates now run for real.
2. **You install Qodo** (~2 min, browser — I cannot do it), then comment
   `/review` on PR #1 by hand. Installing the app after a PR opens does not
   retro-review it. See [qodo.md](qodo.md).
3. **Work the findings.** Every valid High gets fixed or dismissed in writing.
   Then fill in the evidence section with real numbers.
4. **Record the demo.** ~3 minutes, shot list in
   [demo-script.md](demo-script.md), with a no-key fallback.
5. **Then, and only then, consider the exemplar library** (roadmap step 2, E1–E6).
   It is a bigger job than the four items above and it is not what is blocking
   the submission.

---

## Deliberately deferred

Not forgotten — parked, with reasons.

- **Refactor `cli.py` and `designer.py` to delegate to `qa/pipeline.py`.**
  `cmd_qa` / `cmd_deliver` / `cmd_validate` and `_default_spec_stages` /
  `_default_render_stages` each keep their own gate lists. They agree today
  because tests assert they do. One source of truth is better, but this is a
  refactor inside a PR that is already large, and PR #1 is the one being
  reviewed. Do it as its own PR so the diff stays legible.
- **Local TrueForge probe state.** A placeholder `openai` provider with key
  `REPLACE-ME-placeholder-from-schema-probe`, plus an agent named `codex` and
  one session. There is no DELETE route for providers, so it has to be
  overwritten through the UI. Local only, nothing secret.
- **Commit timestamp optics.** Thirteen commits share one timestamp. Cosmetic,
  and rewriting history on a PR under review is worse than the blemish.

---

## The one-line version

The architecture is further along than the evidence for it. Closing that gap is
mostly demo and review work now, not new code.
