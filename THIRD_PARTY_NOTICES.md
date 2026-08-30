# Third-party notices

**Colophon is licensed under the Apache License 2.0.** See [`LICENSE`](./LICENSE).

Colophon stays Apache-2.0. Bringing copyleft code into this repository does
**not** relicence colophon: the obligations below attach only to the specific
third-party files that carry them, never to code we wrote ourselves.

---

## 1. Runtime dependency (not vendored)

| Component | Version | Licence | How it is used |
|---|---|---|---|
| `hyperframes` (npm) | 0.7.86 | Apache-2.0 | Renders the emitted HTML scene document into video. Declared in `colophon/renderers/hyperframes/runtime/package.json`. Used unmodified as a normal dependency. |

A dependency that we consume but do not modify carries no source-disclosure
obligation for our own code.

---

## 2. MIT-licensed components

| Component | Licence | Status |
|---|---|---|
| Video review-rubric *mechanism* (per-dimension floor, hash-bound review context, complete-vector score validation, blind reviewer) | MIT © 2026 Yaxin Luo | Adapted, not vendored. The mechanism is re-implemented from the contract in `colophon/qa/rubric.py`, `colophon/review/context.py`, `colophon/review/critics.py`. The review *dimensions* are colophon's own: the source rubric scores research films and requires a white canvas, which would block colophon's `#0B0B0D` product films. |
| Design-harness *loop mechanism* (bounded designer loop, mechanical-vs-judgment repair routing, repeated-error abort) | MIT © 2026 Yaxin Luo | Adapted, not vendored. Re-implemented in `colophon/harness/designer.py`. Divergence by design: the source routes by **text markers** on a composite blocker list; colophon routes **per finding, by taxonomy code**, through a registry of deterministic remedies (`MECHANICAL_CODES`) so the fails-closed taxonomy stays authoritative. The reference's loop budget (30 turns) and repeated-error threshold (4) are carried over. |

The MIT source was read to learn the contract; no MIT file is copied into this
repository. Where MIT code is vendored later it must keep its copyright notice
and licence text, and be listed here.

---

## 3. MPL-2.0 policy (for vendored code)

Some material we study is **Mozilla Public License 2.0**. MPL-2.0 is
*file-level* copyleft, which is the permissive end of copyleft:

- It **does not spread** to the rest of colophon. Our own files stay Apache-2.0.
- Any MPL-2.0 file we vendor must **keep** its MPL-2.0 licence and licence header.
- The source of those MPL-2.0 files must remain **available** to recipients.
- If we **modify** an MPL-2.0 file, we must note that it has been modified.

So any MPL-2.0 code brought into colophon will:

1. Live under `colophon/vendor/mpl/` and nowhere else, so the boundary is
   mechanical rather than something we have to remember.
2. Retain its original licence header verbatim.
3. Be listed in the table below with its origin and modification status.
4. Be accompanied by the full licence text at `licenses/MPL-2.0.txt`.

### Currently vendored MPL-2.0 files

**None.** No MPL-2.0 source has been copied into colophon.

Where we want something from an MPL-2.0 project, we take its **measurements**
rather than its source — numeric budgets, easing values, timing rules, check
codes. Measured facts and numeric thresholds are not the copyrightable
expression a licence covers, and they are the part that carries the actual
engineering value.

If we later vendor MPL-2.0 code, it lands in `colophon/vendor/mpl/` and is
recorded here.

---

## 4. Trademarks and assets

Third-party fonts, images, and audio referenced by a spec are the property of
their owners and are **not** distributed with colophon. Assets are referenced by
path plus SHA-256, never inlined into the repository.

---

*This file records our understanding of the licences involved. It is not legal
advice — have counsel review before any commercial distribution.*
