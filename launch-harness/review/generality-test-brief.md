# Generality test — the brief handed to the harness (Category 3)

Per the user's pivotal directive: a product the agent has NEVER touched, with NO
.tsx, NO render.json, NO scene graph. This is the ONLY product-side input the
doc-only agent receives (plus `tools/generic-template-pipeline.md`, which
describes how to author and render the video).

## Product
- **Name:** Plink
- **One-line description:** "Plink turns your daily habits into a pinball game
  you actually want to play."
- **Brand color:** `#7C5CFF` (violet)
- **Short feature list (supplied instead of a screenshot):**
  1. Daily routines become pinball launches
  2. Streaks unlock multiball
  3. Friends' boards sync every week

## Constraint (verbatim from directive)
"Have the agent read tools/generic-template-pipeline.md ALONE — no other
context — and build a composition from scratch for this new product. … No
.tsx, no render.json, no scene graph."

This file is the entire brief. The agent under test is allowed to read ONLY
`./tools/generic-template-pipeline.md`.
