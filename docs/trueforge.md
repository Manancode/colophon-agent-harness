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

Colophon works the same way under a different runtime. The seam is MCP over
HTTP and nothing else — see
[ADR 0010](adr/0010-the-harness-is-a-seam-not-a-product.md). Point any client
that speaks MCP at `http://127.0.0.1:8000/mcp` and it can drive the gates.

---

## 0.5 Do you need an API key?

Short answer: **TrueForge, no. The model, yes.** Those are two different
things and the distinction matters.

| Thing | Needs a key? | Why |
|---|---|---|
| TrueForge (the harness) | **No** | `npx @truefoundry/trueforge@latest` starts in standalone mode on port 8790. No signup, no setup wizard, and on macOS it falls back to a local sandbox so it does not even ask for a Daytona key. |
| Colophon (the gates) | **No** | All fourteen gates are deterministic. Zero model calls, in the CLI and over MCP alike. |
| The agent that reads the verdict | **Yes** | The agent is a model. Thinking costs tokens, and somebody's key pays. |

So the sequence is: the harness starts for free, colophon answers for free, and
the first thing that costs money is the moment you ask a model to read the
answer and decide what to do about it. TrueForge will start and serve its UI
happily with no provider configured — it only fails when you create a session,
with `422 Unknown model "<fqn>" — provider not configured`.

Two consequences worth planning around:

* **You can demo the gates with no key at all.** `colophon mcp serve` plus
  `curl` is a complete, working demonstration of the ground truth. The key only
  buys you the agent driving the loop.
* **If you want to skip the model entirely, you can.** `colophon design` runs
  the same repair loop headlessly, from the CLI, with no agent and no key.
  Anything it can fix mechanically, it fixes. The harness is what adds a model
  for the rest — it is not what makes the loop work.

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
python3 scripts/mcp_call.py colophon_gates
```

You should get the 14-gate catalog back as JSON.

> **A bare `tools/list` will not work**, and this trips people up. Streamable
> HTTP is not simple request/response: a client must first `initialize`, keep
> the `Mcp-Session-Id` header the server returns, acknowledge with
> `notifications/initialized`, and only then call a tool. Skip that and every
> call comes back `400 Bad Request: Missing session ID` — which looks exactly
> like a dead server, and is not one.
>
> `scripts/mcp_call.py` does the handshake correctly, and is the thing to copy
> if you are writing your own client. The raw sequence, if you want it:
>
> ```bash
> SID=$(curl -s -D - -o /dev/null -X POST http://127.0.0.1:8000/mcp \
>   -H 'Content-Type: application/json' \
>   -H 'Accept: application/json, text/event-stream' \
>   -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
>        "protocolVersion":"2025-06-18","capabilities":{},
>        "clientInfo":{"name":"curl","version":"1"}}}' \
>   | grep -i '^mcp-session-id:' | tr -d '\r' | awk '{print $2}')
>
> curl -s -X POST http://127.0.0.1:8000/mcp \
>   -H 'Content-Type: application/json' \
>   -H 'Accept: application/json, text/event-stream' \
>   -H "Mcp-Session-Id: $SID" \
>   -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' -o /dev/null
>
> curl -s -X POST http://127.0.0.1:8000/mcp \
>   -H 'Content-Type: application/json' \
>   -H 'Accept: application/json, text/event-stream' \
>   -H "Mcp-Session-Id: $SID" \
>   -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
> ```

---

## 3. Start TrueForge

TrueForge runs in local/standalone mode by default — no signup, no Daytona
key, no setup wizard. On macOS it falls back to a local sandbox automatically.

```bash
npx @truefoundry/trueforge@latest
```

* Requires Node ≥ 22.14 (`node --version`).
* Listens on **port 8790**, and specifically on **`[::1]`** — IPv6 localhost.
  Use `http://localhost:8790`. `http://127.0.0.1:8790` will not connect, which
  looks like a dead server and is not one.
* Default mode is `STANDALONE=true`, so the HTTP API is open without auth.
* Config lives in `~/Library/Application Support/trueforge`; state is SQLite at
  `{data}/db/db.sqlite`.
* If the port is already taken, it exits with `EADDRINUSE` — check
  `lsof -nP -iTCP:8790 -sTCP:LISTEN` rather than starting a second copy.

Open <http://localhost:8790>.

All API paths below are under **`/api/v1/`**.

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

**Or via the HTTP API**, which is what the UI itself calls:

```bash
curl -s -X POST http://localhost:8790/api/v1/settings/mcp-servers \
  -H 'Content-Type: application/json' \
  -d '{"manifest":{"type":"remote","name":"colophon",
       "url":"http://127.0.0.1:8000/mcp",
       "description":"Deterministic QA gates for spec-first video generation."}}'
```

That returns the stored record with `"auth_status":{"status":"not_required"}`.

**Then verify the harness can actually reach colophon** — this is the check that
matters, because a registered-but-unreachable server looks identical in the
settings list:

```bash
curl -s http://localhost:8790/api/v1/mcp-servers/colophon/tools
```

You should get all seven tools back with their descriptions:

```
colophon_gates      List colophon's fourteen QA gates, what each checks, and
                    what artifact it needs before it can run.
colophon_doctor     Check whether this machine has the runtime colophon needs.
colophon_init       Freeze a spec JSON file into a new run directory.
colophon_validate   Run the four spec-level gates on a run.
colophon_plan       Lay the scenes onto the clock and write plan.json.
colophon_qa         Run all fourteen gates on an attempt.
colophon_design     Run the bounded repair loop on a spec.
```

If that list is empty, TrueForge cannot reach your server — check that
`colophon mcp serve` is still running and that the URL scheme is `remote`.

> There is also an npm SDK (`@truefoundry/trueforge-sdk`) with a
> `settings.mcpServers.createOrUpdate` method. Prefer the HTTP call above: the
> SDK surface has moved between versions, and the REST paths are what the UI
> itself uses, so they track the release.

---

## 5. Configure a model

TrueForge starts and serves its UI with **no model configured** — that part is
free. The cost begins when a session needs a model.

**In the UI**: Settings → Model providers → add your key (OpenAI, Anthropic,
TrueFoundry, …). This is the route to use.

**Or via the API**. The shape is stricter than it looks — everything is nested
under `manifest`, the key field is `auth.api_key` (snake case), and `models`
needs at least one entry with `model_id`, `name` and `properties`:

```bash
curl -s -X POST http://localhost:8790/api/v1/settings/model-providers \
  -H 'Content-Type: application/json' \
  -d '{"manifest":{"type":"openai",
       "auth":{"api_key":"sk-..."},
       "models":[{"model_id":"gpt-5.4-mini",
                  "name":"gpt-5-4-mini",
                  "properties":{"context_length":400000}}]}}'
```

Get the exact `model_id` values from
`GET /api/v1/catalogs/model-providers` rather than guessing; they change with
the release. Responses redact the key (`"sk--***REDACTED***-obe"`).

Two rough edges worth knowing before you start:

* **There is no DELETE route for providers.** `POST` creates or overwrites, and
  that is the only method. To remove one, use the UI, or overwrite it. A
  placeholder entry cannot be cleared by POSTing an empty `models` array — the
  API rejects it with `expected array to have >=1 items`.
* **A session needs an agent, not a model name.** `POST /api/v1/sessions`
  rejects `{"title":..., "model":...}` with `Unrecognized keys … at agent`, and
  `GET /api/v1/agents` is empty on a fresh install — so
  `{"agent":{"name":"claude-code"}}` returns `Agent not found: claude-code`.
  Configure the agent through the UI first; the REST path for this is not
  obvious and we have not pinned it down.

**If you would rather not configure a model at all**, skip this step. See
Fallback A in [docs/demo-script.md](demo-script.md) — the gates and the repair
loop both run headlessly with no key.

---

## 5.5 Exactly where the key becomes necessary

This is worth pinning down, because "do you need an API key?" has a more
useful answer than yes or no. Everything below was run against a fresh
TrueForge with **no valid key configured**, and each step succeeded:

| # | Step | Needs a key? |
|---|---|---|
| 1 | Start TrueForge (`npx @truefoundry/trueforge@latest`) | **No** |
| 2 | Start colophon (`colophon mcp serve`) | **No** |
| 3 | Register colophon as an MCP server | **No** |
| 4 | Enumerate the tools through TrueForge | **No** |
| 5 | Call a gate and read a verdict | **No** |
| 6 | Register an agent | **No** |
| 7 | Create a session | **No** |
| 8 | Create a turn and stream its events | **No** |
| 9 | **The model generates its first token** | **Yes** |

Step 9 is where it stops, and it stops cleanly:

```
turn.done  status: error
           message: Request failed (401): Incorrect API key provided: sk-throw***robe.
           metrics: { total_input_tokens: 0, total_output_tokens: 0, total_tokens: 0 }
```

So the harness, the socket, the tools, the session and the event stream are all
free and all verifiable before you spend anything. **The key buys you the
model, and nothing else.**

If you want to reproduce that ladder, the calls are:

```bash
# 6. register an agent (model name must be a fully-qualified "provider/model")
curl -s -X POST http://localhost:8790/api/v1/agents \
  -H 'Content-Type: application/json' \
  -d '{"name":"codex","manifest":{"model":{"name":"openai/gpt-5-4-mini"}}}'

# 7. create a session
SID=$(curl -s -X POST http://localhost:8790/api/v1/sessions \
  -H 'Content-Type: application/json' -d '{"agent":{"name":"codex"}}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['id'])")

# 8. send a turn, streamed as SSE
curl -s -X POST "http://localhost:8790/api/v1/sessions/$SID/turns" \
  -H 'Content-Type: application/json' -H 'Accept: text/event-stream' \
  -d '{"input":[{"type":"user.message","content":"Call colophon_validate on /tmp/colophon-demo"}]}'
```

Two shapes that are easy to get wrong: the model name **must** be
`provider/model` (a bare `gpt-5` is rejected with *"Model name must be a fully
qualified provider/model"*), and the turn payload takes `input` as an **array
of discriminated objects** — `{"type":"user.message","content":"…"}`. A
top-level `"message"` field is accepted and then silently ignored, producing a
turn that fails instantly with `Invalid prompt: messages must not be empty`.

`turn.done` carries a `state` with `status`, `message` and `metrics`, so a
failed turn is readable without watching the stream.

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

Below is a real transcript, captured against `examples/broken-duration.json`
with the server running on `127.0.0.1:8000`. Three calls, in order.

**1. Freeze the spec into a run.** The hash is taken here and follows every
artifact afterwards.

```json
{
  "ok": true,
  "run_dir": "/private/tmp/colophon-demo",
  "spec_sha256": "9caaf63f1d450e8f829e9afda6aaa5028d2e989c6f8bb60ea775eb8ef1745e8e",
  "scene_count": 2,
  "claim_count": 4,
  "normalize_notes": ["s1 accept_treatment hero-centered",
                      "s2 accept_treatment feature-rows"]
}
```

**2. Validate it.** Blocked, with each blocker naming the gate that produced it:

```json
{
  "ok": true, "scope": "spec", "state": "blocked",
  "spec_sha256": "9caaf63f…",
  "gates_run": 4, "gates_passed": 1,
  "blockers": [
    { "stage": "spec_validate",       "code": "spec.scene.duration",
      "message": "scene s2: duration_s must be > 0, got 0.0" },
    { "stage": "timeline_continuity", "code": null,
      "message": "scene s2 has non-positive duration" },
    { "stage": "delivery_contract",   "code": null,
      "message": "timeline duration 3.00s is outside [5.00, 180.00]" },
    { "stage": "delivery_contract",   "code": null,
      "message": "scene s2 lasts 0.00s, under the 0.50s minimum" }
  ],
  "warnings": [
    { "stage": "narrative_order", "code": null,
      "message": "last scene has role 'capability'; expected 'cta'" }
  ]
}
```

Note the shape: not "this looks bad", but four checkable claims, three of which
carry `code: null` because their stages do not name their failures yet. That is
the honest state of the taxonomy, not a bug.

**3. Change one number and run the same gate again.** `s2.duration_s: 0 → 3.5`:

```json
{
  "ok": true, "scope": "spec", "state": "ready_with_warnings",
  "spec_sha256": "e62b798170cbb78be2027527e70a49b471d059738209523ed04af2015fdbb807",
  "gates_run": 4, "gates_passed": 4,
  "blockers": [],
  "warnings": [
    { "stage": "narrative_order", "code": null,
      "message": "last scene has role 'capability'; expected 'cta'" }
  ]
}
```

Two things to point at. `gates_passed` went 1 → 4 with one number changed. And
**the spec hash changed** — `9caaf63f…` → `e62b7981…` — which is the whole
provenance story in one line: the verdict is attached to a specific document,
and a different document is a different verdict.

That transcript **is** the evidence for "the harness is doing real work". Save
it — copy it into the README's Qodo/TrueForge section, and screen-record it for
the demo.

### Verifying the harness can reach colophon

Independently of any agent, TrueForge can enumerate the tools itself:

```bash
$ curl -s http://localhost:8790/api/v1/mcp-servers/colophon/tools
colophon_gates      List colophon's fourteen QA gates, what each checks, and
                    what artifact it needs before it can run.
colophon_doctor     Check whether this machine has the runtime colophon needs.
colophon_init       Freeze a spec JSON file into a new run directory.
colophon_validate   Run the four spec-level gates on a run.
colophon_plan       Lay the scenes onto the clock and write plan.json.
colophon_qa         Run all fourteen gates on an attempt.
colophon_design     Run the bounded repair loop on a spec.
```

This proves the socket is wired. It does not prove an agent used it — for that
you need a session, and therefore a configured agent and model.

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

**Ports.** colophon `:8000` (IPv4 `127.0.0.1`), TrueForge `:8790`
(IPv6 `[::1]`). Both on localhost, so no firewall or tunnel is involved — but
mind the address family; see step 3.

**Sandbox may be unavailable inside a sandbox.** `GET /api/v1/capabilities`
reports what is actually enabled:

```json
{"data":{"sandbox":{"enabled":false},
         "skill":{"enabled":false,"reason":"Skills run in a sandbox, which is not configured."},
         "settings":{"enabled":true}}}
```

If you run TrueForge from inside another agent's sandbox, macOS will refuse the
nested `sandbox-exec` (`Operation not permitted`) and the local sandbox fallback
is unavailable — which also disables skills, since they run in a sandbox. Run
TrueForge from a normal terminal and it works. Check `/api/v1/capabilities`
before concluding anything is broken.

**Models are redacted in responses.** A registered provider comes back with
`"api_key":"sk--***REDACTED***-obe"`, so confirming a key is stored is safe to
paste into a transcript.
