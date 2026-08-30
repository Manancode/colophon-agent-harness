# Running colophon inside TrueForge

Colophon is an instrument, not an employee. It tells you what is wrong with a
video spec; it does not decide what to do about it. **TrueForge** is the
environment an agent works inside — the loop, the tool calling, the sandbox,
the approvals, the session state — so it is the natural place to put an agent
in front of colophon's gates.

This document is the runbook. Follow it top to bottom and you will have an
agent reading a spec, calling colophon's gates, seeing failures, editing, and
re-running.

---

## 0. What "running on TrueForge" means here

There are two ways to bolt two systems together, and only one of them is worth
anything.

**The thin wrapper (what this is *not*).** An agent calls a model, the model
says "this video looks good", and the pipeline ships. Nothing is checked, the
harness is decoration, and the failure mode is a shipped defect.

**The harness doing real work (what this *is*).** The agent calls
`colophon_validate`, gets back a structured verdict naming the gate and the
failure code, edits the spec, and calls it again. The loop is the product.
TrueForge supplies the loop; colophon supplies the ground truth. The model
never gets a veto — the deterministic gates hold it.

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

---

## 1. Install

```bash
cd /Users/piedpiper/colophon

# colophon itself, with the optional MCP transport
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev,mcp]'

# sanity check: the CLI should list an `mcp` command
colophon --help
colophon doctor
```

Requires Python ≥ 3.11, plus `node`, `ffmpeg` and `ffprobe` on `PATH`
(`colophon doctor` will tell you which are missing).

---

## 2. Start colophon's MCP server

```bash
colophon mcp serve --host 127.0.0.1 --port 8000
```

Leave it running. You should see the server bind on port 8000. It exposes the
MCP endpoint at `http://127.0.0.1:8000/mcp`.

Quick check that it is alive:

```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 2000
```

You should get back seven tools: `colophon_gates`, `colophon_doctor`,
`colophon_init`, `colophon_validate`, `colophon_plan`, `colophon_qa`,
`colophon_design`.

---

## 3. Start TrueForge

TrueForge runs in local/standalone mode by default — no signup, no Daytona
key, no setup wizard. On macOS it falls back to a local sandbox automatically.

```bash
npx @truefoundry/trueforge@latest
```

* Requires Node ≥ 22.14 (`node --version`).
* Listens on **port 8790**.
* Default mode is `STANDALONE=true`, so the HTTP API is open without auth.
* Config lives in `~/Library/Application Support/trueforge`; state is SQLite at
  `{data}/db/db.sqlite`.

Open <http://localhost:8790>.

---

## 4. Register colophon as an MCP server

**In the UI** (Settings → MCP servers → Add):

| Field | Value |
|---|---|
| Type | `remote` |
| Name | `colophon` |
| URL | `http://127.0.0.1:8000/mcp` |

TrueForge's MCP client only supports **remote (HTTP)** servers — its server
type enum has no stdio variant, which is why colophon ships an HTTP transport
rather than a `command` you spawn.

**Or via the SDK**, if you want it scripted:

```js
import { TrueForgeClient } from '@truefoundry/trueforge-sdk';

const client = new TrueForgeClient({ baseUrl: 'http://localhost:8790' });

await client.settings.mcpServers.createOrUpdate({
  manifest: {
    type: 'remote',
    name: 'colophon',
    url: 'http://127.0.0.1:8000/mcp',
    description: 'Deterministic QA gates for spec-first video generation.',
  },
});
```

Install the SDK with:

```bash
npm install @truefoundry/trueforge-sdk
```

> The SDK surface moves between versions. If a method name above does not
> resolve, check `node_modules/@truefoundry/trueforge-sdk/dist` for the current
> shape — the UI path in step 4 always works and is the safer route.

---

## 5. Configure a model

TrueForge starts fine with **no model configured**; it only fails when you
create a session (`422 Unknown model "<fqn>" — provider not configured`). So
add a provider before your first run:

**In the UI**: Settings → Model providers → add your key (OpenAI, Anthropic,
TrueFoundry, …).

**Or via the API**:

```bash
curl -s -X PUT http://localhost:8790/settings/model-providers \
  -H 'Content-Type: application/json' \
  -d '{"providers":[{"type":"openai","apiKey":"sk-...","models":["gpt-4o"]}]}'
```

---

## 6. Give the agent something real to do

Two specs ship with the repo for exactly this purpose:

| File | What it is |
|---|---|
| `examples/two-scene.json` | Valid. Two scenes, four grounded claims. Gates should clear it. |
| `examples/broken-duration.json` | Same spec with scene `s2`'s `duration_s` set to `0`. Blocked, and mechanically repairable. |

Start with the broken one — it gives the agent something real to fix and makes
the loop visible in a single screen of transcript.

Then, in a new TrueForge chat, paste a prompt like this (substituting the
absolute path to your checkout):

```
You have colophon tools. Do not guess whether a spec is good — measure it.

1. Call colophon_gates and read what each gate needs.
2. Call colophon_init with spec <absolute path to the spec> and run dir
   /tmp/colophon-run.
3. Call colophon_validate. Report the blockers verbatim.
4. Fix the spec file to clear them. Re-run colophon_validate.
5. Repeat until state is `ready` or `ready_with_warnings`.

Read the `hint` field before acting on a blocker. If it says nothing has been
emitted yet, that is not a defect you caused — emit, then re-read.
```

To make the loop interesting, start from a **broken** spec: copy a good one and
set a scene's `duration_s` to `0`. The agent should find the blocker, fix the
duration, and converge in two or three calls.

---

## 7. What you should see

The agent's transcript should show repeated, alternating calls:

```
colophon_validate  →  state: blocked
                      blockers: [{ stage: spec_validate,
                                   code: spec.scene.duration,
                                   message: "…duration must be positive…" }]
                      hint: "fix the blockers named above, then re-run"

   [agent edits spec.json]

colophon_validate  →  state: ready
                      gates_run: 4, gates_passed: 4
```

That transcript **is** the evidence for "the harness is doing real work". Save
it — copy it into the README's Qodo/TrueForge section, and screen-record it for
the demo.

---

## 8. Notes and gotchas

**No tool prompts.** None of colophon's tools carry `@write` or `@destructive`
annotations. TrueForge's default approval list is `["@write", "@destructive"]`
and *unannotated tools are exempt*, so the loop will not stall on a permission
prompt. The tools that do write (`colophon_init`, `colophon_plan`,
`colophon_qa`, `colophon_design`) are documented as writing, and only ever
write inside the run directory you name.

**Optional: install colophon as a skill.** `skills/colophon/SKILL.md` in this
repo tells an agent how to drive the gates — the loop, how to read a verdict,
and the specific mistakes to avoid. To use it, push this repo (it is public) and
add it in TrueForge under **Settings → Skills → Add**, using the repo's HTTPS
GitHub URL.

Two constraints worth knowing:

* TrueForge accepts skills **from a git URL only** — an HTTPS GitHub or GitLab
  URL. Local paths and `file://` are rejected, so you cannot point it at your
  checkout.
* It **never parses `SKILL.md` frontmatter.** The name and description come
  from whatever you POST in the manifest, not from the file. So the file's
  *contents* are what the agent reads; the file's header is decoration.

If you would rather not set up a skill, the prompt in step 6 carries the same
instructions and works fine.

**Colophon still runs with TrueForge deleted.** The MCP server is a socket, not
a dependency. `colophon deliver` works end to end with this file removed.

**Ports.** colophon `:8000`, TrueForge `:8790`. Both on localhost, so no
firewall or tunnel is involved.
