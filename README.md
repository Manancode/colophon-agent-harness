# colophon

I built colophon because AI-generated launch videos keep shipping with defects nobody caught: text spilling off screen, a scene flashing for a fifth of a second, a claim that traces back to nothing. It's a fixed checklist of **14 deterministic gates** a video has to clear before it ships. None of the gates call a model. When one fails, it tells you the exact rule and the line to change, not "this feels off."

It runs as an MCP tool server inside an agent harness (I use TrueForge), so an agent can call the checks, read a precise verdict, and fix the spec.

## What it does

You hand colophon one JSON spec. It freezes the plan, renders the video, then runs the 14 gates. Every gate fails closed: if it sees something it doesn't recognise, it blocks rather than waving it through.

```
brief + brand -> canonical spec -> editable project (HTML/CSS) -> render -> 14 gates -> review + repair
```

## The 14 gates

Every gate is deterministic and order-independent. None of them call a model.

| # | gate | catches |
|---|------|---------|
| 1 | `spec_validate` | made-up values, missing required fields, malformed structure |
| 2 | `timeline_continuity` | timeline gaps, undeclared overlaps, scenes past the end |
| 3 | `narrative_order` | call to action in the opening beat (advisory) |
| 4 | `static_html` | broken markup before rendering |
| 5 | `canvas_audit` | wrong background, unreadable text |
| 6 | `scene_structure` | a scheduled scene that draws nothing, or a missing asset |
| 7 | `claim_grounding` | an on-screen claim with no source you supplied |
| 8 | `ai_slop_detector` | cream-and-orange palette, sparkle glyphs, neon glow, ticker bars |
| 9 | `color_consistency` | accent colour not matching your brand |
| 10 | `centerpiece_invariant` | more than one thing moving per scene |
| 11 | `motion_accessibility` | flicker-fast motion, ignoring reduced-motion |
| 12 | `delivery_contract` | wrong size/fps, length outside envelope, sub-second scene |
| 13 | `motion_pixel_velocity` | motion too slow to glide |
| 14 | `media_contract` | file on disk not matching the plan |

Plain-English walkthrough: `docs/understand.md`.

## Quick start

Prereqs: Python 3.11+, ffmpeg on PATH, Node.js 20+ (only for the bundled HyperFrames renderer).

```bash
git clone https://github.com/Manancode/colophon-agent-harness.git
cd colophon-agent-harness
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Run the example end to end:

```bash
colophon init      examples/cadence/spec.json  runs/cadence-01
colophon deliver    runs/cadence-01            --review
# video:  runs/cadence-01/attempts/01/artifact/launch-video.mp4
# report: runs/cadence-01/delivery-report.json
```

Serve the gates as MCP tools:

```bash
colophon mcp serve --host 127.0.0.1 --port 8000
# http://127.0.0.1:8000/mcp
```

Wire it into TrueForge: Settings -> MCP servers -> Add, type `remote`, url `http://127.0.0.1:8000/mcp`. Add a model provider under Settings -> Model providers. Runbook: `docs/trueforge.md`.

## The seven tools

| tool | what it returns |
|------|----------------|
| `colophon_gates` | all fourteen checks and what each needs first |
| `colophon_doctor` | whether this machine has node, ffmpeg, ffprobe |
| `colophon_init` | a frozen run folder and the plan's SHA-256 fingerprint |
| `colophon_validate` | the four spec-level checks (no rendering needed) |
| `colophon_plan` | the timeline: when each scene starts and ends |
| `colophon_qa` | all fourteen checks on a rendered attempt |
| `colophon_design` | the fix-and-recheck loop, and how far it got |

Every answer is `{ state, blockers, warnings, hint }`. The tools carry no `@write` or `@destructive` annotation, so the loop never stalls on a permission prompt.

You don't need an API key for the harness or the checks. Both run with zero model calls. Only the agent that reads the verdict needs a key.

## How it fits TrueForge

colophon is an instrument, not an employee: it reports what's wrong, it doesn't decide what to do. TrueForge is the harness, the loop, the tool calling, the sandbox. colophon runs inside it as an MCP tool server. Delete `mcp_server.py` and TrueForge and `colophon deliver` still runs end to end; anything that speaks MCP over HTTP can drive the checks. See ADR 0010.

## launch-harness

This repo also ships `launch-harness/` — the agent-native harness that actually drives video generation. It's the other half of the loop: colophon (above) is the QA instrument; launch-harness is the generation side.

You hand it a brief. It routes to a single local, key-free render engine — one fact-based branch decides: footage present → cut it; absent → compose from scratch — then renders, then grades its own work against an **8-dimension gate** (hook, capability accuracy, brand consistency, motion, narration, subtitles, CTA, length). Every dimension must score at least 4/5, backed by evidence (pixel samples, media probes, source checks), never "looks good to me." Under 4 and it goes back to fix that one thing; no averaging past a failure.

Two rules baked in from the start: telemetry stays off (nothing leaves the machine) and no new API keys.

`launch-harness/SKILL.md` is the brain, `launch-harness/RUNBOOK.md` is the end-to-end test, `launch-harness/review/` holds the gate and the real scorecards. Merged in PR #3.

## Design decisions

The shape of the system is captured in ten ADRs under `docs/adr/`. Read them before proposing a change:

- 0001 the plan is the source of truth
- 0002 seconds are authoritative; frames are derived
- 0003 never silently drop unknown keys
- 0004 the layout vocabulary is bounded
- 0005 grounding is checked against emitted output, not intent
- 0006 renderer adapter seam: emit, then render
- 0007 the agent runtime is a caller, not a dependency
- 0008 explicit overlaps; no speed multiplier
- 0009 colophon runs inside an agent harness as an MCP tool server
- 0010 the harness is a seam, not a product

## Contributing

PRs welcome. Keep the guarantees intact:

- new layouts and animations go in `presentation/` with a written reason, never inline in a renderer
- any new gate must be deterministic and order-independent
- `runs/` is derived data and gitignored, don't commit it
- keep this README in sync with any change to a public surface (tool, gate, ADR, CLI flag)

```bash
pip install -e ".[dev]"
python3 -m pytest tests -q
```

## License

Apache-2.0. See `LICENSE`. colophon drives HyperFrames (Apache-2.0) as an external process through the adapter seam in `renderers/`.

Qodo reviewed the substantive PRs: [PR #1](https://github.com/Manancode/colophon-agent-harness/pull/1) (merged) and [PR #2](https://github.com/Manancode/colophon-agent-harness/pull/2) (merged), which hardened provenance and the server's filesystem/auth surface.
