# Empty-footage decisive test — 2026-09-01

**Question:** can the footage toolkit be the single front door? Pointed at a
folder with zero raw footage and only a brief, does it recognise there is
nothing to cut and hand off cleanly to the launch composition workflow?

**Verdict: FAIL. It hard-errors. There is no zero-footage path.**

---

## Setup

Folder `~/launch-runs/empty-footage-test/` containing **one file** — `BRIEF.md`
(a cal.com launch brief: 20 seconds, 1920x1080, "footage: none supplied, nothing
to cut — this has to be built from scratch"). Zero media files.

## What was run

The footage toolkit's own inventory step, verbatim from its `SKILL.md` §The process, step 1:
"`ffprobe` every source. `transcribe_batch.py` on the directory.
`pack_transcripts.py` to produce `takes_packed.md`."

### 1. Enumerate sources

```
MEDIA_FILE_COUNT=0
```

Nothing to `ffprobe`.

### 2. `transcribe_batch.py <videos_dir>`

```
TRANSCRIBE_BATCH_EXIT=1
--- output ---
no videos found in ~/launch-runs/empty-footage-test
```

### 3. `pack_transcripts.py --edit-dir ./edit`

```
PACK_EXIT=1
--- output ---
no .json files in ~/launch-runs/empty-footage-test/edit/transcripts
```

### 4. What landed in `edit/`

```
edit/
└── transcripts/   (empty)
```

An empty shell. No `takes_packed.md`, no EDL, no artifact, no handoff.

## Two independent confirmations

### A. The skill text has no zero-footage branch

```
$ grep -niE "no footage|zero |empty|nothing to cut|from scratch|product-launch|hand ?off|no video" SKILL.md
106:- **Speaker handoffs** benefit from air between utterances. ...
244:- ≤ 2 accent colors, ~40% empty space, minimal chrome
```

Both hits are unrelated (audio advice; layout advice). **No match for any
zero-footage, composition-only, or hand-off concept.**

### B. The composition engine is only an *overlay* engine there

Every mention of the composition engine in the toolkit's `SKILL.md` is about
animation **slots inside an existing cut** — never the whole-video path:

- line 65: "Node.js + npm available if the session needs … slots"
- line 205: listed as one of four *animation* tool options
- line 210: "For … slots, scaffold the slot inside `edit/animations/slot_<id>/` … Point the EDL overlay `file` at the actual rendered path"
- line 214: "Invent hybrids if useful"

The toolkit treats it as a way to render an overlay that gets composited **onto a
cut**. There is no instruction anywhere to make it the primary path when there is
no footage.

## The failure is structural, not a missing API key

`transcribe_batch.py` calls `find_videos()` and errors on empty **before**
`load_api_key()` is ever reached. So exit 1 is caused purely by the absence of
footage — the missing transcription key is not a confounding variable. This
test is clean.

## Conclusion

**"One pipeline" is not real as specified.** The toolkit cannot be the single
front door, because it has no degradation path for the empty-footage case —
neither in its instructions nor in its code.

The branch has to live **one layer up**, in our harness, and it has to be
evaluated before the toolkit is invoked. That is now Step 0 of `SKILL.md`:

| Media files in folder | Path |
|---|---|
| 0 | Path B — composition only |
| ≥ 1 | Path A — cut the footage |

Verified dry run after the fix:

```
empty-footage-test:    0 media file(s) -> PATH B (composition only)
footage-present-test:  1 media file(s) -> PATH A (cut the footage)
```

---

## Related finding — the chat shell cannot point at the toolkit

The chat shell's MCP client expects **remote HTTP** servers:

```json
{ "pm": "https://<host>/mcp/pm/server", "crm": "https://<host>/mcp/crm/server" }
```

Its shipped catalog (`catalog/mcp-catalog.yaml`) is **100% `type: remote`** with
HTTPS URLs — no local/stdio servers at all.

The footage toolkit ships **no MCP server** (grep for `modelcontextprotocol` /
`FastMCP` / `mcp_server` across the package: zero hits). It is a skill —
instructions plus scripts — not a server.

So "point it at the toolkit" is **not a config change**. It requires building an
MCP server that wraps the toolkit and either hosting it remotely or adding local
transport support to the shell. Recorded as a finding, not worked around.
