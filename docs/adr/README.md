# Architecture Decision Records

Short, dated records of decisions that are expensive to reverse. New ADRs are
appended; existing ones are amended, not rewritten.

| # | Decision | One-line reason |
|---|---|---|
| [0001](0001-canonical-spec-is-source-of-truth.md) | Canonical spec is source of truth | Our first document was plan + project + assets + timeline at once, so nothing could be validated or hashed independently |
| [0002](0002-seconds-are-authoritative-frames-are-derived.md) | Seconds authoritative, frames derived | A `playbackSpeed: 1.25` turned an advertised 22.3s into 17.9s |
| [0003](0003-never-silently-drop-unknown-keys.md) | Never silently drop unknown keys | A permissive normaliser ate `treatment`; the bug surfaced as "the renderer is wrong" |
| [0004](0004-bounded-treatment-grammar.md) | Bounded scene grammar: 6 roles × 2 treatments | Applying one layout six times is coherent and forgettable; role-matched treatments make the same copy read as an argument |
| [0005](0005-grounding-is-checked-against-emitted-output.md) | Grounding checked against emitted output | A spec can be valid while the video lies; `unbound_visible_number` only exists after emission |
| [0006](0006-renderer-adapter-seam-emit-then-render.md) | Renderers behind an emit/render seam | Generate-then-render keeps the spec renderer-agnostic, so a second renderer needs no spec change |
| [0007](0007-agent-runtime-is-a-caller-not-a-dependency.md) | The agent runtime is a caller, not a dependency | A pipeline you cannot run by hand is a pipeline you cannot trust |
| [0008](0008-explicit-overlaps-no-speed-multiplier.md) | Explicit overlaps; no speed multiplier | Real scene boundaries overlap 6–12 frames with `matchCut` — a strictly adjacent timeline cannot express that |

## recurring themes

Three of these came from the same root cause: **a number that nobody chose.**
The 22.3s that was really 17.9s (0002), the treatment that silently vanished
(0003), and the unbound number that no claim supported (0005). In each case the
fix was not better validation of intent — it was making the value impossible to
express implicitly.
