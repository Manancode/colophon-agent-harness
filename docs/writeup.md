# Colophon — write-up

*Supporting material for the TrueForge Agent Harness Hackathon submission. The
technical detail lives in the [README](../README.md); this is the argument.*

---

## The problem, stated narrowly

An agent can now write a launch video end to end. Nothing in that pipeline can
tell you whether the video will *look* good, and "looks good" is not one
problem — it is two, and only one of them is hard:

| Kind of wrong | Example | Who can catch it |
|---|---|---|
| **Measurable** | A scene is 0.2 s long. Text overflows its frame. The accent is one hue off the brand token. A claim on screen has no source in the brief. | a computer |
| **Judgement** | The movement feels cheap. | a human |

The first kind is solved. Fourteen deterministic gates catch it, no model
calls, and every finding names the gate and the failure code that produced it.

The second kind is not solved, and the usual approach makes it worse: ask a
vision model "is this video good?" and take the answer. On boundary defects
visual QA scores **F1 11–42** (UI-Lens, CVPR 2026). That is close to a coin
flip on precisely the subtle failures that matter. Asking is not checking.

## The bet

Taste becomes tractable if you stop letting the agent author from nothing and
give it a **closed vocabulary** instead. Colophon's grammar is 6 roles, 12
treatments, 3 motions. From that, two things follow:

1. **You cannot lint a pixel, but you can lint a spec.** A motion is a number —
   `400 ms`, a `60 ms` stagger, a scale of `1.05`. So taste is a parameter you
   set, version and enforce, not a feeling you re-litigate every render.
2. **A verdict can be located instead of interpreted.** "The pulse feels cheap"
   resolves onto one of three dials — vocabulary, parameters, precondition —
   and one edit makes it true for every future video.

> Our job is not to read the corpus. It is to smelt it into enums.
> A blog post is read once; a schema enum is applied a million times.

## What the agent actually does

The agent is not the generator. It is the thing that closes a loop:

```
call a gate  →  read a verdict naming the failure  →  change something  →  look again
```

That loop is the product. It is the missing piece, because colophon is an
instrument rather than an employee: it reports what is wrong and deliberately
does not decide what to do about it.

## How we used TrueForge

**TrueForge is the runtime the agent works inside.** It supplies the loop, the
tool calling, the sandbox, the approvals and the session state. Colophon runs
*inside* it as an MCP tool server — seven tools over streamable HTTP — and
supplies the ground truth.

```
   ┌──────────────────────── TrueForge (the harness) ────────────────────────┐
   │                                                                         │
   │   agent ──calls──> colophon_validate ──> { state, blockers, hint }      │
   │     ▲                                              │                    │
   │     └──── edits the spec, re-runs the gate ─────────┘                   │
   └─────────────────────────────────────────────────────────────────────────┘
                                   │
                         HTTP (MCP), localhost
                                   │
                    colophon mcp serve  →  the 14 gates
```

Two things about this are deliberate.

**The model never gets a veto.** The deterministic gates decide whether a run
ships. A model may comment on taste; it cannot alone trigger a repair. This is
not distrust of models as such — it is the F1 11–42 number above.

**TrueForge is a seam, not a dependency.** Colophon is itself a harness: it
owns the loop, the verdict and the repair router. TrueForge owns where the
agent sits while it works. Delete `mcp_server.py` and TrueForge together, and
`colophon deliver` still runs end to end. Anything that speaks MCP over HTTP
can drive the gates; TrueForge is today's choice, not a lock-in. See
[ADR 0010](adr/0010-the-harness-is-a-seam-not-a-product.md).

### Do you need an API key?

**TrueForge: no. Colophon: no. The model: yes.**

`npx @truefoundry/trueforge@latest` starts in standalone mode on port 8790 with
no signup and no setup wizard; on macOS it falls back to a local sandbox, so it
does not ask for a sandbox key either. Colophon's fourteen gates make zero model
calls. The first thing that costs money is the moment you ask a model to read a
verdict and decide what to do about it — and TrueForge starts and serves its UI
happily with no provider configured, failing only at session creation with
`422 Unknown model "<fqn>" — provider not configured`.

The practical consequence: **the ground truth is demoable with no key at all.**
`colophon mcp serve` plus `curl` is a complete demonstration. The key buys you
the agent driving the loop, not the loop itself. And `colophon design` runs the
same repair loop headlessly from the CLI — no agent, no key, no harness.

## What we built for this submission

* `colophon/mcp_server.py` — seven tools as plain functions plus a registration
  table, so they are unit-testable without an MCP library installed.
* `colophon/qa/pipeline.py` — one source of truth for the two canonical gate
  sets. Each gate's "what artifact does it need" classification is **derived
  from its own signature**, not hand-listed, so a gate that grows a `video_path`
  parameter becomes a video-tier gate with no edit anywhere.
* `colophon mcp serve` — the HTTP transport. HTTP specifically because
  TrueForge's MCP client only supports `remote` servers; its server-type enum
  has no stdio variant.
* `docs/trueforge.md` — the full runbook.
* `skills/colophon/SKILL.md` — agent operating instructions.
* `examples/two-scene.json` and `examples/broken-duration.json` — one valid
  spec and one deliberately broken, so the loop has something real to fix.

## The detail we are proudest of

Every verdict carries a `hint`, and it is load-bearing rather than decorative.

Before an artifact exists, several gates report *"nothing to check"*, and the
taxonomy counts that as a blocker — correctly, because failing closed is the
entire point. An agent reading only the blocker list concludes it broke
something and starts "fixing" a spec that was fine.

We shipped that hint with a bug in it. `colophon_validate` runs only the four
spec-level gates, which never read an artifact — but it was returning the
*"nothing has been emitted yet"* hint anyway. That explanation was impossible
for the gates that had run, and it would have pointed an agent at the wrong
problem. It is fixed (`validate` now passes `scope="spec"`) with a regression
test asserting the hint does not mention emitting.

Worth stating plainly: **the failure mode the hint exists to prevent was found
in the hint itself**, by running the tool by hand rather than by reading the
tests. All 445 tests passed with that bug in the tree.

## Honest limitations

* **The demo video is not recorded yet.** The shot list is in
  [docs/demo-script.md](demo-script.md).
* **Qodo review evidence is pending.** Everything before this work was a direct
  push to `main` and cannot be retro-fitted with a review trail. That is
  disclosed in the README rather than papered over.
* **Rendering is not exercised in this environment.** The renderer's
  `node_modules` is not provisioned here, so the render-dependent gates
  degrade to spec-level with an explicit attestation recorded in the run.
  The degradation is honest — it never silently passes.
* **The grammar is small on purpose.** 3 motions is a starting point, not a
  finished vocabulary. Step 2 of the roadmap (bounded vocabulary + curated
  exemplars) is in progress.

## What we would defend

The claim is not "an agent made a video". It is narrower and stronger:

> Given a closed vocabulary, most of what people call taste is measurable —
> and the parts that are not should be the only thing left to argue about.

The gates are the asset. A runtime is a place to run them.
