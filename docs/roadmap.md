# Colophon — Roadmap and Decision Rules

Last revised 2026-08-29.

This is not a feature wishlist. It is a **gated plan**: each step unlocks the
next, and the response to every possible outcome is written down *before* the
experiment runs. That is what separates an experiment from a hope.

---

## 1. Why the plan is gated

The open question is not answerable by reading:

> **Can a bounded grammar plus a curated exemplar library produce output a
> human rates as good, without a repair loop?**

That is a measurement. Every further paper, blog post, and repository answers a
*different* question. Additional reading has crossed from "reduces risk" to
"feels productive."

### The literature is raw ore, not a syllabus

There are thousands of practitioner write-ups about generation quality, growing
daily. We will never read all of them, and we should not try. They are people
writing down taste — the same phenomenon as a hand-edited scene document. The
difference is that prose cannot be linted and a schema can.

> **The job is not to read the corpus. It is to smelt it into enums.**
> Every principle mined becomes a schema constraint, an allowed enum value, or
> an exemplar. Once encoded, it is enforced on every generation forever. A blog
> post is read once; a schema enum is applied a million times.

So: keep mining opportunistically, in the background. Never gate the build on it.

---

## 2. Why a spec is the right substrate

The value of a canonical spec is not editability. It is that **a spec is the only
representation where taste can be validated *before* rendering.**

- You cannot lint a pixel.
- You cannot diff an MP4.
- You cannot reject a rendered frame for violating a brand rule *before* paying
  to render it.

Everything else follows. Constrained decoding then guarantees *validity*, which
frees the model's budget for *taste*.

### One hard constraint

Constrained decoding can **destroy** generation quality if the schema's field
order fights the model's natural generation order. Tam et al. 2024
(https://arxiv.org/html/2408.02442v1) measured JSON-mode collapsing GPT-3.5's
Last Letter accuracy from **56.74 → 1.78**, and Gemini-1.5-Flash from
**65.45 → 0.67**, because 100% of responses emitted `answer` before `reason` —
killing the reasoning trace.

**Rule:** the schema exposes an `intent` / `reason` field **first**, before
structure, motion, and params. Field order is a taste decision, not formatting.

---

## 3. The exemplar library

A curated library of hand-validated specs is the moat. It is the one asset a
competitor cannot clone from a blog, because it is our validated taste,
concretized.

**Size correction: 20–30 is the size of the *library*, not of the *prompt*.**

| Evidence | Number |
|---|---|
| KATE (Liu et al. 2021, arXiv:2101.06804) — kNN retrieval vs random | SST-2→IMDB +5.5; ToTTo BLEU +41.9% rel.; nearest-10 vs farthest-10 **46.0 vs 31.0 EM** |
| Many-shot ICL (DeepMind, arXiv:2404.11018) | Peaks are task-specific: MATH ~125, GPQA 125, XSum **50 then declines**, planning saturates at **10** |
| Noise robustness (arXiv:2405.17264) | At 60% noisy exemplars: **−29–39 EM, −25–35 BLEU**. And **K=8 was worse than K=2 under noise** |
| MMR diversity rerank (SIGIR 2025, arXiv:2505.01842) | Won 17/24 settings, significant in only 6/24; helps at k ≥ 7, α ≥ 0.5 |

### Five rules for the library

1. **Retrieve k = 3–8 per call. Never stuff 30.** Long-context many-shot results
   are for short-output classification, not long-form artifact generation.
2. **Admission gate = deterministic QA, not taste.** In *generation* (unlike
   classification), noisy exemplars are catastrophic. One bad spec in a k=5
   prompt is 20% contamination. Gate on passing all seven gates.
3. **Scaffold-and-edit, do not blend.** Retrieve **one** exemplar as a verbatim
   starting document and instruct *localized edits*; use the others as
   contrastive context. Mechanistically justified in §4.
4. **One fixed brand anchor + k−1 diverse.** Style consistency across a batch
   comes from a shared anchor, not a bigger prompt.
5. **Pin the ordering in version control.** Ordering is second-order but
   unstable; never let it be a free variable.

### Guarding the library

- **Bad-exemplar detection:** local perplexity ranking — score each spec against
  its k=4 semantic neighbours; if it sits in the higher-perplexity half, flag for
  review (recovers +18.75 EM on the reference task). Run on every commit to the
  library.
- **Leave-one-out ablation** on a fixed eval set: if removing a spec improves the
  average, prune it.

---

## 4. The pastiche risk — and why scaffold-and-edit is the fix

In-context learning implicitly implements **Bayesian model averaging / ridge
regression** over exemplars (arXiv:2305.19420). More exemplars literally means
averaging over more hypotheses — **regression to the mean**. Aligned models
compound it with typicality bias: direct prompting retains only **23.8%** of
base-model diversity (arXiv:2510.01171).

That is the mechanism behind "generated output looks generic."

**The mitigation is scaffold-and-edit.** Retrieve one verbatim document and edit
it. Do not ask the model to synthesize across many. This is the single
highest-leverage design decision in the system.

Secondary mitigations: hard-cap k at 3–8; verbalized sampling for candidate
generation (+25.7% human-rated diversity on the reference task) then filter with
the grammar.

---

## 5. Multi-agent is not a goal. It is a response to measured failure.

Add an agent when **one agent demonstrably fails at a separable subtask** — not
because multi-agent is the state of the art.

And critically: the contribution at stage 5 is *meta-harness optimization* —
learning the harness itself from rollout traces. We are at stage 1. **You cannot
optimize a harness that has no metric yet.** Building the optimizer before the
thing to optimize is the classic error, and it is the temptation in front of us
right now.

### The sequence

```
1. METRIC        seven deterministic gates + fingerprint + human rating   done
2. GRAMMAR       bounded vocabulary + curated exemplars                   in progress
3. MEASURE       generate 20, score failures by category                  gated on 2
4. DECOMPOSE     add a second agent only at a measured failure point      gated on 3
5. OPTIMIZE      only now: meta-harness / self-improvement                gated on 4
```

Step 1 is done. Step 2 is in progress. Steps 3–5 are gated on evidence we do not
yet have.

Supporting evidence for decomposition *when justified*: a
Planner→Coder→Critic split with progressive scope refinement
(line→block→global) works — but each role there existed because a separable
failure mode had been measured first.

---

## 6. The experiment (timeboxed)

**Goal:** answer the one open question. One week.

| Step | Work | Output |
|---|---|---|
| E1 | Hand-craft **8 exemplar specs** across the 6 roles, all passing 7/7 QA. Render each. | 8 MP4s + 8 specs in `exemplars/` |
| E2 | Stand up the similarity index; retrieve k=5; scaffold-and-edit. | retriever + prompt builder |
| E3 | Generate **20 specs** for 4 unseen products (5 each) with one agent, scaffold-and-edit. | 20 specs, 0 rendered |
| E4 | Run all 20 through QA. **Do not render.** | pass rate + failure histogram by gate |
| E5 | Render the 6 highest-scoring and the 3 lowest. | 9 MP4s |
| E6 | **A human** rates all 9 blind, 1–5, with one line each. | the ground truth we do not have |

### Decision rule, agreed in advance

- If ≥60% pass QA **and** mean human rating ≥3.5 → the grammar is sound; scale
  the exemplar library to 30 and build repair.
- If QA passes but ratings are low → the grammar is valid but *tasteless*. The
  problem is the treatment library, not the architecture. Expand treatments.
- If QA fails on a single dominant gate → that gate is the next agent. Now there
  is evidence for decomposition.
- If failures are uniform → the IR is wrong. Revise the schema before adding
  anything.

**Each outcome has a different, pre-committed response.** That is what makes it
an experiment.

---

## 7. Standing decisions

1. **Colophon stays independent.** Port capabilities, not codebases.
2. **One renderer.** A second adapter waits until its licence is modelled; the
   Apache-2.0 HTML/CSS renderer remains the only one.
3. **Deterministic QA is the moat.** Published visual-QA benchmarks put VLM
   detection of boundary defects at F1 11–42, so the visual reviewer handles
   taste only and never alone triggers repair.
4. **Exemplar admission is QA-gated.** No spec enters the library without 7/7.
5. **`intent` first** in the schema, before structure and motion.
6. **Research continues opportunistically in the background** — smelted into
   enums, never gating the build.
