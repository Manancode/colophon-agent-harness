# Demo script — ~3 minutes

Record at 1920×1080, full screen, terminal + browser. Speak plainly; the point
is to show the harness **working**, not to explain the architecture.

**The one thing the video must prove:** a judge has to see the harness doing
real work, not a thin wrapper around a model call. So the middle section — the
agent calling a gate, getting a structured failure, fixing it, and re-running —
is the whole video. Everything else is context.

---

## Setup, before you hit record

```bash
cd /Users/piedpiper/colophon
source .venv/bin/activate

# terminal 1
colophon mcp serve --host 127.0.0.1 --port 8000

# terminal 2
npx @truefoundry/trueforge@latest
```

Register `http://127.0.0.1:8000/mcp` in TrueForge (Settings → MCP servers →
Add → type `remote`). Add a model provider.

Open the broken spec so it is visible in an editor pane:
`examples/broken-duration.json`.

---

## 0:00 – 0:20 · The problem

**On screen:** nothing but a terminal. Run the naive path.

```bash
colophon deliver runs/naive --renderer hyperframes
```

**Say:** "Here's the normal way this goes. An agent writes a video plan, a
renderer turns it into a file, and it ships. Nothing checked it. If a scene
lasts zero seconds, or the accent colour is wrong, or a number on screen has no
source — you find out after you've published."

**Cut.**

---

## 0:20 – 0:50 · Two processes, one socket

**On screen:** side-by-side. Left: `colophon mcp serve` bound on :8000. Right:
TrueForge on :8790.

Show the seven tools on screen:

```bash
python3 scripts/mcp_call.py colophon_gates
```

Do **not** use a bare `tools/list` curl here — it returns
`400 Bad Request: Missing session ID`, because streamable HTTP requires an
`initialize` handshake and an `Mcp-Session-Id` header first. A judge watching
you hit that error will reasonably conclude the server is broken. Use the
script; it does the handshake.

**Say:** "Colophon runs *inside* TrueForge. It's not calling out to a model for
an opinion — it's serving fourteen deterministic gates as tools. TrueForge is
the environment: the loop, the tools, the sandbox, the session. Colophon is the
ground truth it can check against."

---

## 0:50 – 2:10 · The loop *(this is the video)*

**On screen:** the TrueForge chat UI, full screen. Leave it wide enough that the
tool calls and their JSON payloads are readable.

Paste:

```
You have colophon tools. Do not guess whether a spec is good — measure it.

1. Call colophon_gates and read what each gate needs.
2. Call colophon_init with spec <repo>/examples/broken-duration.json
   and run dir /tmp/colophon-demo.
3. Call colophon_validate. Report the blockers verbatim.
4. Fix the spec file to clear them. Re-run colophon_validate.
5. Repeat until state is `ready` or `ready_with_warnings`.

Read the `hint` field before acting on a blocker. If it says nothing has been
emitted yet, that is not a defect you caused.
```

**Narrate over the transcript as it happens:**

- "First it asks what the gates are." *(point at `colophon_gates`)*
- "It freezes the spec into a run — the spec is hashed, and that hash follows
  every artifact afterwards."
- "Now `colophon_validate`. And it comes back **blocked**." *(pause on the
  payload)* "Look at what it actually got: a state, a list of blockers naming
  the gate and the failure code, and a hint. Not 'this looks bad' — a specific,
  checkable claim."
- "It edits the spec." *(show the file diff)*
- "It re-runs." *(pause on `state: ready`, `gates_run: 4`)*

**Then the important beat.** Hand it a problem colophon can see but cannot
mechanically fix — change a claim's text to something ungrounded, or set a
duration below the delivery floor. Show the loop stopping in `blocked` rather
than guessing.

**Say:** "It stops rather than guessing. That's deliberate — an agent that
silently rewrites your spec is worse than one that admits it's stuck."

---

## 2:10 – 2:40 · All fourteen, on a real artifact

**On screen:** terminal.

```bash
colophon deliver runs/demo --review
colophon qa runs/demo
```

**Say:** "Four of the gates run on paper — they only need the spec, so they're
free. The other ten need something real: the emitted HTML, or the encoded MP4.
Here they all are, in one pass, with the verdict at the bottom."

Point at the `blocked` / `ready_with_warnings` / `ready` line and the eval
fingerprint.

---

## 2:40 – 3:00 · Why this isn't a wrapper

**On screen:** the ASCII diagram from the README, or the TrueForge transcript
frozen on a tool call.

**Say:** "The distinction that matters: the agent never gets a veto. It can
propose, but the deterministic gates decide — and when the taxonomy doesn't
recognise a problem, it blocks rather than waving it through. Research on
visual QA by vision model puts F1 at eleven to forty-two on exactly the subtle
failures that matter. That's a coin flip. So the model gets a voice on taste
and no vote on shipping."

**End card:** repo URL.

---

## Notes

- **Do not speed up the middle section.** That loop is the evidence. If the
  demo has to be 3:30 to keep it readable, keep it.
- **Keep the JSON readable.** Zoom in or raise the font before recording; a
  judge who can't read the payload can't see the work.
- **If the agent converges in one call**, use `examples/broken-duration.json`
  *and* break something else in the same file so there are at least two
  iterations on screen.
- **If a tool call fails**, leave it in. Showing the harness recover is more
  convincing than showing it be perfect.

---

## Fallback A — no model key

You do not need a model key to show the loop working. The harness and the
gates are both free; the key only buys you the *agent*.

If you would rather not add a provider, record this instead of section 0:50–2:10:

```bash
# terminal: the gates, driven directly, no model involved
colophon design examples/broken-duration.json
```

That runs the same repair loop headlessly. It reports the blockers, applies the
mechanical fix, re-runs the gates, and stops — with no agent and no key. Then
break something it *cannot* fix mechanically and run it again, so you get the
"it stops rather than guessing" beat.

You can also drive the MCP server directly to prove the socket is real and the
tools are live:

```bash
python3 scripts/mcp_call.py colophon_validate '{"run_dir":"/tmp/colophon-demo"}'
```

That handles the `initialize` → `Mcp-Session-Id` → `notifications/initialized`
handshake that streamable HTTP requires. A bare `tools/call` curl gets
`400 Bad Request: Missing session ID` and proves nothing.

**Say:** "Everything you've just seen runs with no model and no key. The agent
is what TrueForge adds on top — it's the thing that reads this verdict and
decides what to try next. The gates were never the part that needed a model."

That is a weaker video for the hackathon (rule 3 wants the harness visible),
but it is a complete, honest demo and it ships today.

## Fallback B — rendering is not provisioned

`colophon deliver` needs the renderer's `node_modules`, which is not installed
in this checkout. Section 2:10–2:40 will fail until you provision it once:

```bash
colophon render runs/demo --renderer hyperframes
```

If that fails on network, cut section 2:10–2:40 and spend the time on the loop
instead. The loop is the evidence; the fourteen-gate pass is supporting
material. Do not fake the output.
