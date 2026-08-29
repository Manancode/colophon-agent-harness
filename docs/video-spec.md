# Canonical video spec

`spec_version: "0.1"`

The spec is the only source of truth for a video. It is renderer-agnostic,
content-addressed where it matters, and small enough to read and hand-edit —
the shipped Cadence example is 8 KB.

## Top level

```jsonc
{
  "spec_version": "0.1",
  "spec_id": "cadence-launch-01",
  "title": "Cadence — launch video",
  "canvas":     { ... },
  "brand":      { ... },
  "timeline":   { ... },
  "assets":  [ ... ],
  "claims":  [ ... ],
  "scenes":  [ ... ],
  "notes":   "free text"
}
```

Unknown keys are **rejected**, never dropped. `reject_unknown_keys()` exists
because a silent drop is the worst failure mode here: an earlier normaliser
rebuilt scenes from a fixed key set, so when `treatment` was
added it vanished without an error and the video rendered as if the field had
never existed.

## `canvas`

| field | type | notes |
|---|---|---|
| `width`, `height` | int | output resolution |
| `fps` | int | one of 24, 25, 30, 48, 50, 60 |
| `background` | hex | the audit colour; the root and every clip must match it |

Maps 1:1 onto a rendered composition.

## `brand`

| field | type | notes |
|---|---|---|
| `name` | string | product name |
| `tokens` | object | must contain `bg`, `fg`, `accent` |
| `voice` | object | narrator/rate metadata, unused by V0 rendering |

`assets/brand.py` derives the rest — `muted`, `soft`, `hair`, `panel`, `bar`,
`dot`, `accent_soft`, `accent_edge` — and the renderer exposes every one as a
CSS custom property. Treatments may only use those variables, never raw
colours. That is the entire styling contract, and it is why a re-brand is a
spec edit rather than a code edit.

## `timeline`

| field | type | default | notes |
|---|---|---|---|
| `policy` | `"adjacent"` \| `"explicit"` | `adjacent` | `explicit` rejected in V0 |
| `overlap_s` | float | `0.0` | how much consecutive scenes overlap |
| `transition` | `"cut"` \| `"match_cut"` \| `"fade"` | `cut` | |
| `transition_ms` | int | `400` | duration of the entry motion |

`overlap_s` exists because scene overlaps are real. In the launch document we
first measured, all five boundaries overlapped by 6–12 frames, each carrying a
`matchCut`. A strictly-adjacent timeline cannot express that. The Cadence
example uses `0.25s`, which is ~7 frames at 30fps.

There is deliberately **no `playback_speed`**. That document carried
`playbackSpeed: 1.25`, silently turning an advertised 22.3s into an actual
17.9s. Speed belongs in a scene's own timing, never as a document multiplier.

## `assets`

| field | type | notes |
|---|---|---|
| `asset_id` | id | unique |
| `kind` | `image`\|`audio`\|`video`\|`font`\|`data` | |
| `path` | string | relative to the example dir; must stay inside the project root |
| `sha256` | string | verified at resolve time; empty means "fill it in" |
| `meta` | object | free-form |

No remote URLs. A render that depends on `https://cdn.example.com/logo.png` is
not reproducible — the URL can change, expire, or serve something else, and the
video would change without the spec changing.

## `claims`

| field | type | notes |
|---|---|---|
| `claim_id` | id | unique |
| `text` | string | the exact copy |
| `kind` | `title`\|`narration`\|`stat`\|`quote` | |
| `source` | string | where it came from, e.g. `brief.md#problem` |

A claim is the only legitimate source of visible copy. Every scene binds a
title claim and a narration claim; nothing else is in scope for that scene.

## `scenes`

| field | type | notes |
|---|---|---|
| `scene_id` | id | unique |
| `role` | enum | `hook` `problem` `capability` `differentiator` `proof` `cta` |
| `treatment` | string | must be legal for the role |
| `duration_s` | float | the **only** timing input |
| `title_claim_id` | id \| null | must have `kind: title` |
| `narration_claim_id` | id \| null | |
| `asset_ids` | list | |
| `treatment_params` | object | treatment-specific knobs (unused in V0) |
| `renderer_hints` | object | advisory only; never authoritative |

Starts are **derived** by the timeline layer, never authored. A scene cannot
drift out of alignment with its neighbours because it does not know where it
is.

### Roles

| role | intent |
|---|---|
| `hook` | Earn the next ten seconds. Name the product and the change it makes. |
| `problem` | Name the pain the viewer already has, in their words. |
| `capability` | Show the mechanism. What the product actually does. |
| `differentiator` | Say why this and not the thing they use today. |
| `proof` | Evidence: a number, a quote, an outcome. |
| `cta` | One action, stated once, unmistakably. |

### Treatments (two per role, twelve total)

| role | treatments |
|---|---|
| hook | `hero-centered`* · `hero-split` |
| problem | `statement-left`* · `statement-right` |
| capability | `feature-rows`* · `ui-frame` |
| differentiator | `statement-right`* · `compare-columns` |
| proof | `quote-card`* · `stat-hero` |
| cta | `cta-command`* · `cta-panel` |

\* baseline — used when a scene omits `treatment`.

### Preconditions

Preconditions are the grammar refusing to lie.

| treatment | precondition | why |
|---|---|---|
| `stat-hero` | a numeral exists in the bound claims | it sets a number huge; without one it would have to invent it |
| `compare-columns` | copy contains a contrast cue | two opposed columns imply a comparison the narration must actually make |
| `feature-rows`, `ui-frame` | narration splits into ≥ 2 clauses | rows come from splitting copy, not from invention |

Failures raise. They never silently fall back to the baseline — if the planner
asked for a treatment, it should hear that it did not get it.

## Grounding rules

Checked against the **emitted project**, not the spec, because a treatment can
be well-behaved in the spec and still emit copy no claim licenses.

- `unbound_visible_number` — every number on screen must appear in a claim
  bound to that scene.
- `title_mismatch` — the visible `<h1>` must be identical to its claim.
- `narration_clause_dropped` — every content word of the narration must appear
  in the output.

The first rule is why a claim reading "forty percent" blocks `stat-hero`: the
digits `40` are not in the claim, so rendering them would be fabrication.

## Fingerprints

- `spec_sha256` — sha256 of the canonical JSON of the whole spec.
- `scene_sha256` — sha256 of one scene plus the canvas, brand, claims and
  assets it references.

The second is what makes repair provably local: after a targeted edit, only the
edited scenes' hashes should change.
