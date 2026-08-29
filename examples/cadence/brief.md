# Cadence — product brief

## Positioning

For engineering teams, Cadence turns a red pipeline into a ranked list of fixes.

## Problem

Every week your team loses hours to failures buried in CI logs.

## Capability

Cadence reruns failed jobs, labels them flaky, and clusters every failing test.

## Differentiator

Other tools show logs. Cadence ranks fixes by engineering time saved.

## Proof

Teams using Cadence cut mean time to green by forty percent.

## CTA

Install the GitHub App. No YAML. Get your first ranked fix queue in five minutes.
Visit cadence.dev.

---

## Notes for the agent

Every claim in `spec.json` traces to a heading above. The `source` field on each
claim records which heading it came from, so if a claim ever looks wrong you can
walk it back to the brief in one hop.

Two things to know about this particular script:

- The proof copy spells the number out ("forty percent") rather than writing
  "40%". That is deliberate. It means `stat-hero` — the treatment that sets a
  numeral huge — is **blocked** for this scene, because the bound claims contain
  no digits and the treatment would have to invent one. `quote-card` is used
  instead. If you want the stat treatment, change the claim text to "40%"
  first; do not change the treatment to work around it.
- The CTA narration is one sentence with four clauses. `cta-command` splits it
  into four stacked lines, so the line count follows the copy rather than
  being hard-coded.
