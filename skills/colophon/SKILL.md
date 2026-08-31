# Using colophon's QA gates

You have colophon tools. They are deterministic: the same spec always produces
the same verdict, and no gate calls a model. That is why they can be trusted
over your own judgment about whether a video spec is good.

**Never assert a spec is good because it looks good to you. Measure it.**

## The loop

1. `colophon_gates` — read what each gate checks and what artifact it needs
   before it can tell the truth. Do this first, once.
2. `colophon_init` with the spec path and a run directory. This freezes the spec
   and stamps its SHA-256 onto every artifact that follows.
3. `colophon_validate` — the four spec-level gates. Cheap, no rendering. This is
   the one to loop on while editing.
4. Read the blockers. Fix the spec. Re-run.
5. Stop when `state` is `ready` or `ready_with_warnings`.

Once something has been emitted and rendered, `colophon_qa` runs all fourteen
gates on the artifact. `colophon_design` runs a bounded repair loop that fixes
what it can prove is safe to fix.

## Reading a verdict

Every answer is the same shape:

```
state      blocked | ready_with_warnings | ready
blockers   [{ stage, code, message }]   must be fixed
warnings   [{ stage, code, message }]   advisory, still ships
hint       one sentence: what to do next
```

A blocker's `code` may be `null`. That is not a missing field — it means the
taxonomy has not been taught to name that failure yet, and colophon counts
unnamed failures as blockers on purpose. Treat `null` as "colophon cannot
classify this, so it cannot be fixed mechanically", not as "no problem".

## The mistake to avoid

**Read the `hint` before you act on a blocker.**

Before anything has been emitted, several gates report *"nothing to check"* —
and that counts as a blocker, because failing closed is the point. If you read
only the blocker list you will conclude you broke something and start "fixing" a
spec that was fine. The hint says so when that is what is happening: emit, then
re-read.

## What you must not do

- **Do not edit the video.** Edit the spec. The project and the MP4 are derived
  and get regenerated; the spec is the source of truth.
- **Do not clear a blocker by loosening the spec to match a bad render.**
  If a gate says a scene is too short, the scene is too short.
- **Do not decide readiness yourself.** You can propose; the gates decide.
  A model gets a voice on taste and no vote on shipping.
- **Do not keep iterating on the same blocker.** If the same blockers come back
  unchanged three times, stop and report. That is the signal the problem needs
  a human, not more turns.

## Fixing things

- Non-positive or missing scene duration → the design loop repairs this
  mechanically. Use `colophon_design`.
- An unknown treatment or role → the grammar is closed. Pick a value from the
  twelve treatments and six roles; do not invent one.
- A claim with no source → every number and claim on screen must trace back to
  a claim you were given. Cut the copy or find the source. Do not supply one
  from memory.
