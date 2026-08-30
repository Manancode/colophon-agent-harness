"""Emit a canonical spec as an editable HyperFrames project.

The output is a single self-contained ``index.html`` plus an asset folder.
That file *is* the editable video project: a human or an agent can open it,
change a line, and re-render — the workflow that worked well by hand on the
launch document, but here against a validated spec instead of a 760 KB
blob of inlined app HTML.

Renderer contract notes, each learned the hard way:

* the composition root needs ``data-composition-id``;
* each scene is a ``<section class="clip">`` carrying ``data-start``,
  ``data-duration`` and ``data-track-index``;
* the canvas audit walks *ancestors only*, so the root and every clip must
  carry the exact brand background with ``background-image: none`` and
  opacity 1. Descendants are unconstrained, which is where all visual
  variation lives;
* motion must sit on descendant wrappers, never on the clip itself, and must
  push in from an opacity floor rather than fade from 0, or the first and
  last frames of a scene come out blank;
* every font family needs an ``@font-face`` with a ``local()`` source, or
  the linter hard-rejects the render.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from ...assets.brand import to_css
from ...presentation.treatments import TREATMENTS
from ...spec.schema import Scene, VideoSpec
from ...timeline.plan import SceneWindow, TimelinePlan

#: Motion must never start from fully transparent. Pushing in from 0.85 keeps
#: every frame populated, which is what stopped blank frames at scene
#: boundaries.
OPACITY_FLOOR = 0.85

#: The baseline entrance is a property of the MOTION, not of the timeline's
#: transition. Conflating the two meant a hard cut (``transition_ms == 0``)
#: collapsed the entrance to 1ms, which silently turned the whole fade-rise
#: baseline into a no-op: every scene cut in with no motion at all.
#: The convention is an entrance of roughly 400ms (12f at 30fps), which also
#: matches the 400ms this project already used via ``match_cut``.
ENTER_MS = 400

#: Per-word stagger and travel for the word-sweep motion.
# Stagger is 100ms (3f at 30fps) so consecutive words never fire <2 frames
# apart — a <2-frame stagger reads as a single jumble, not a cascade.
# Travel is 16px over WORD_TRAVEL_MS (480ms @30fps = 14.4f -> 1.11px/frame).
# That clears the per-frame pixel-velocity floor (>=1px/frame); the
# previous 8px was 0.56px/frame and stuttered (sat still, then jumped).
WORD_STAGGER_MS = 100
WORD_TRAVEL_MS = 480

#: The thinking-pulse entrance. This is the one motion that had drifted: it
#: used to run 1200ms on a single ease-in-out, which is *outside* the closed
#: duration band the design is built on. blakecrosley.com's Motion Grammar
#: caps motion at ~300-400ms (page/modal band) and the whole project's thesis
#: is "the deletion test outranks the taste test" — a 1200ms pulse is exactly
#: the noise that test is meant to delete. We pin it to 400ms and give it real
#: weight (an anticipatory dip + overshoot) instead of raw scale, so it reads
#: as Mass & Weight rather than a cheap throb. PULSE_MS is substituted into the
#: stylesheet the same way OPACITY_FLOOR is.
PULSE_MS = 400


def _entrance_ms(spec: VideoSpec) -> int:
    """How long the baseline entrance runs, in milliseconds.

    A non-zero ``transition_ms`` is honoured so existing specs render exactly
    as they did. Only the degenerate 0 (a hard cut) falls back to ENTER_MS,
    because a cut between scenes should not delete the entrance *within* one.
    """
    transition_ms = spec.timeline.transition_ms
    return transition_ms if transition_ms > 0 else ENTER_MS


def _offset_ms(window: Any) -> int:
    """Scene start in milliseconds — the anchor every per-scene motion needs.

    A CSS ``animation-delay`` is measured from when the element is rendered,
    not from when its scene starts. Without this offset every descendant
    motion fires at page load and is long finished before scene 2 is on
    screen -- the motion grammar only ever worked on scene 1.
    """
    return int(round(window.start_s * 1000))


_MONO_FAMILIES = ("SFMono-Regular", "Menlo", "Consolas", "Liberation Mono")
_SANS_FAMILIES = (
    "-apple-system",
    "BlinkMacSystemFont",
    "Segoe UI",
    "Helvetica Neue",
    "Arial",
    "Noto Sans",
)


def _font_faces() -> str:
    """Declare every named family the stacks reference.

    HyperFrames hard-rejects ``font_family_without_font_face``. ``local()``
    satisfies it from the OS with no network fetch, so the render stays offline
    and deterministic. Generic families (sans-serif, monospace) need nothing.
    """
    return "".join(
        f"@font-face{{font-family:'{name}';src:local('{name}')}}"
        for name in (*_MONO_FAMILIES, *_SANS_FAMILIES)
    )

_SANS_STACK = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI','Helvetica Neue',"
    "Arial,'Noto Sans',sans-serif"
)
_MONO_STACK = "'SFMono-Regular',Menlo,Consolas,'Liberation Mono',monospace"


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _split_clauses(text: str) -> list[str]:
    parts = re.split(r",\s*|\s+and\s+", text or "")
    return [p.strip().rstrip(".") for p in parts if p and p.strip()]


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _stat_token(text: str) -> str | None:
    m = re.search(r"\d[\d,]*(?:\.\d+)?\s*%?", text or "")
    return m.group(0).strip() if m else None


def _stat_label(text: str, token: str) -> str:
    rest = (text or "").replace(token, "", 1)
    rest = re.sub(r"\s+", " ", rest).strip(" ,.-")
    return rest


# --------------------------------------------------------------------------
# stylesheet
# --------------------------------------------------------------------------

_BASE_CSS = """
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg)}
[data-composition-id]{position:relative;overflow:hidden;background:var(--bg)}
.clip{
  position:absolute;inset:0;display:flex;align-items:center;
  background:var(--bg);background-image:none;opacity:1;
}
.scene-body{width:100%;height:100%;display:flex;align-items:center;padding:0 96px}
/* Two animations per scene. The entrance only spans the transition, but the
   composition's length is taken from the furthest animation extent, so a
   transition-only animation truncates the video to
   last_scene_start + transition. The hold is an invisible no-op spanning the
   scene's full window, which is what makes the render as long as the plan.
   It animates outline-color with no outline-style set, so nothing is ever
   painted and it cannot fight the entrance over opacity or transform. */
.clip-motion{
  animation-name:colophon-in,colophon-hold;
  animation-fill-mode:both,none;
  animation-timing-function:cubic-bezier(.22,.61,.36,1),linear;
}
@keyframes colophon-in{
  from{opacity:OPACITY_FLOOR;transform:translateY(14px)}
  to{opacity:1;transform:none}
}
@keyframes colophon-hold{
  from{outline-color:transparent}
  to{outline-color:transparent}
}
h1{
  margin:0;font-family:SANS;font-weight:700;letter-spacing:-.02em;
  color:var(--fg);font-size:82px;line-height:1.08;
}
/* word-sweep motion: per-word transform settle, staggered. Opacity is
   deliberately left to the parent .clip-motion fade-rise — stacking
   fractional opacities drops the whole subtree (the bug that forced the
   colophon-hold workaround). The .m-word-sweep class scopes the rules so a
   scene that does not opt in gets nothing. */
.m-word-sweep .word{
  display:inline-block;
  animation-name:word-sweep-in;
  animation-fill-mode:both;
  animation-timing-function:cubic-bezier(.2,.75,.34,.94);
}
@keyframes word-sweep-in{
  from{transform:translateY(16px)}
  to{transform:none}
}
/* thinking-pulse motion: the scene's single centerpiece does ONE weighted
   pulse (scale only), suggesting "the agent is initializing / the number is
   being decided".

   The target is [data-centerpiece], which the RENDERER stamps on exactly one
   element per scene. It is not a CSS selector guess like ".figure, .glyph,
   h1" — that matched two elements on quote-card (the big glyph AND the small
   attribution line) and pulsed both, which reads as a glitch rather than an
   emphasis. The renderer knows which element is the anchor; CSS does not.

   Same opacity-omitted constraint as word-sweep: the parent .clip-motion
   fade-rise already animates opacity, and stacking fractional opacities
   drops the subtree.

   The old pulse ran 1200ms on a single ease-in-out. That is outside the
   closed duration band the design is built on (blakecrosley.com caps motion
   at ~300-400ms) and carried no Mass & Weight — which is exactly why it
   reads as "cheap". The replacement stays inside the band (PULSE_MS = 400)
   and earns its weight from the curve, not the duration:
     0%   Anticipation — a slight wind-up dip (ease-in)
     30%  Strike        — overshoot past rest (ease-out)
     62%  Settle        — fall back below rest (ease-in)
     100% Rest
   Per-keyframe easing means the entrance and exit are distinct, the way a
   real object would speed into and ease out of an emphasize. */
.m-thinking-pulse [data-centerpiece]{
  animation-name:thinking-pulse-in;
  animation-fill-mode:both;
  animation-duration:PULSE_MSms;
  animation-timing-function:ease-in-out;
  transform-origin:center;
  display:inline-block;
}
@keyframes thinking-pulse-in{
  0%   {transform:scale(.92);animation-timing-function:cubic-bezier(.4,0,.7,1)}
  30%  {transform:scale(1.06);animation-timing-function:cubic-bezier(.22,.61,.36,1)}
  62%  {transform:scale(.97);animation-timing-function:cubic-bezier(.4,0,.6,1)}
  100% {transform:none}
}
/* Accessibility: honour the user's OS reduced-motion preference. Every motion
   in colophon is decorative emphasis on an otherwise static layout, so it can
   be removed without losing information. This is the concrete accessibility
   gate the Motion Grammar essay calls a first-class requirement. */
@media (prefers-reduced-motion: reduce){
  .clip-motion{animation-name:none}
  .m-word-sweep .word{animation:none}
  .m-thinking-pulse [data-centerpiece]{animation:none}
}
p{margin:0;font-family:SANS;color:var(--muted);font-size:30px;line-height:1.45}
.eyebrow{
  font-family:MONO;font-size:15px;letter-spacing:.22em;text-transform:uppercase;
  color:var(--accent);margin:0 0 22px;
}
.rule{height:1px;background:var(--hair);border:0;margin:0}
.vrule{width:1px;align-self:stretch;background:var(--hair)}
.panel{
  background:var(--panel);border:1px solid var(--hair);border-radius:14px;padding:34px 38px;
}
.chip{
  display:inline-flex;align-items:center;gap:10px;font-family:MONO;font-size:19px;
  color:var(--fg);background:var(--accent_soft);border:1px solid var(--accent_edge);
  border-radius:999px;padding:10px 20px;
}
.dot{width:9px;height:9px;border-radius:50%;background:var(--dot);flex:0 0 auto}
.row{display:flex;align-items:flex-start;gap:18px;padding:16px 0}
.row+.row{border-top:1px solid var(--hair)}
.mono{font-family:MONO}
.accent{color:var(--accent)}
"""

#: The problem and differentiator roles each have a right-aligned statement
#: block. They are visually identical but they are *different treatments*, so
#: the rules are written once and specialised per id instead of copy-pasted.
#: align-items is center, NOT stretch. The grid's implicit row stretches to the
#: full frame height, so a stretch child fills it and its copy flows from the
#: top, which pinned these blocks high and made them read as centred rather
#: than right-anchored. .vrule carries its own align-self:stretch, so the rule
#: still runs the full height beside the vertically centred block.
_RIGHT_STATEMENT_CSS = """
.t-KEY .scene-body{display:grid;grid-template-columns:1fr 14px;gap:44px;align-items:center}
.t-KEY .body{grid-column:1;text-align:right;padding:8px 0}
.t-KEY h1{font-size:92px}
.t-KEY p{margin-top:34px;margin-left:auto;max-width:1000px}
"""


def _right_statement_css(key: str) -> str:
    return _RIGHT_STATEMENT_CSS.replace("KEY", key)


_TREATMENT_CSS: dict[str, str] = {
    # ---- hook -----------------------------------------------------------
    "hero-centered": """
.t-hero-centered .scene-body{flex-direction:column;justify-content:center;align-items:center;text-align:center}
.t-hero-centered h1{font-size:150px;letter-spacing:-.045em}
.t-hero-centered p{margin-top:26px;max-width:1180px;text-align:center}
""",
    "hero-split": """
.t-hero-split .scene-body{display:grid;grid-template-columns:1.05fr 1fr;gap:88px;align-items:center}
.t-hero-split h1{font-size:132px;letter-spacing:-.04em}
.t-hero-split .side{border-left:1px solid var(--hair);padding-left:56px}
""",
    # ---- problem --------------------------------------------------------
    # align-items is center, NOT stretch. Same reason as _RIGHT_STATEMENT_CSS:
    # the stretched implicit row pushed the copy to the top of the frame, which
    # is what made "statement-left" render as top-right. .vrule keeps its own
    # align-self:stretch so the rule still spans the full height.
    "statement-left": """
.t-statement-left .scene-body{display:grid;grid-template-columns:14px 1fr;gap:44px;align-items:center}
.t-statement-left .body{padding:8px 0}
.t-statement-left h1{font-size:92px;max-width:1240px}
.t-statement-left p{margin-top:34px;max-width:1000px}
""",
    "statement-right": _right_statement_css("statement-right"),
    # ---- capability -----------------------------------------------------
    "feature-rows": """
.t-feature-rows .scene-body{flex-direction:column;justify-content:center;gap:44px}
.t-feature-rows .rows{width:100%;max-width:1500px}
.t-feature-rows .row{font-family:SANS;font-size:31px;color:var(--fg);line-height:1.35}
""",
    "ui-frame": """
.t-ui-frame .scene-body{flex-direction:column;justify-content:center;gap:40px}
.t-ui-frame .frame{
  width:100%;max-width:1420px;background:var(--panel);
  border:1px solid var(--hair);border-radius:16px;overflow:hidden;
}
.t-ui-frame .chrome{
  display:flex;gap:8px;align-items:center;padding:15px 20px;
  border-bottom:1px solid var(--hair);background:var(--panel);
}
.t-ui-frame .chrome i{width:11px;height:11px;border-radius:50%;background:var(--bar);display:block}
.t-ui-frame .rows{padding:16px 34px 26px}
.t-ui-frame .row{font-family:MONO;font-size:25px;color:var(--fg)}
""",
    # ---- differentiator -------------------------------------------------
    "rebuttal-right": _right_statement_css("rebuttal-right"),
    "compare-columns": """
.t-compare-columns .scene-body{flex-direction:column;justify-content:center;gap:46px}
.t-compare-columns .cols{display:grid;grid-template-columns:1fr 1.35fr;gap:0;width:100%;max-width:1560px}
.t-compare-columns .col{padding:34px 40px}
.t-compare-columns .col:first-child{border-right:1px solid var(--hair)}
.t-compare-columns .col p{font-size:29px}
.t-compare-columns .col.lead p{color:var(--fg)}
""",
    # ---- proof ----------------------------------------------------------
    "quote-card": """
.t-quote-card .scene-body{flex-direction:column;justify-content:center;gap:0;max-width:1420px}
.t-quote-card .glyph{font-family:SANS;font-size:150px;line-height:.7;color:var(--accent);margin-bottom:12px}
.t-quote-card blockquote{
  margin:0;font-family:SANS;font-size:48px;line-height:1.3;color:var(--fg);font-weight:500;
}
.t-quote-card .attr{
  margin-top:34px;padding-top:24px;border-top:1px solid var(--hair);
}
.t-quote-card .attr p{font-size:24px}
""",
    "stat-hero": """
.t-stat-hero .scene-body{flex-direction:column;justify-content:center;align-items:flex-start;gap:6px}
.t-stat-hero .figure{
  font-family:SANS;font-size:230px;font-weight:800;letter-spacing:-.05em;
  line-height:.95;color:var(--accent);
}
.t-stat-hero .caption{font-family:SANS;font-size:40px;color:var(--fg);max-width:1200px}
.t-stat-hero p{margin-top:26px;max-width:1000px}
""",
    # ---- cta ------------------------------------------------------------
    "cta-command": """
.t-cta-command .scene-body{flex-direction:column;justify-content:center;gap:36px}
.t-cta-command .lines{display:flex;flex-direction:column;gap:14px}
.t-cta-command .line{
  font-family:MONO;font-size:27px;color:var(--fg);
  display:flex;align-items:center;gap:16px;
}
.t-cta-command .line .prompt{color:var(--accent)}
.t-cta-command .url{margin-top:18px}
""",
    "cta-panel": """
.t-cta-panel .scene-body{justify-content:center;align-items:center}
.t-cta-panel .panel{
  display:flex;flex-direction:column;align-items:center;gap:26px;text-align:center;
  padding:72px 96px;min-width:900px;
}
.t-cta-panel p{max-width:760px}
""",
}


# --------------------------------------------------------------------------
# scene bodies
# --------------------------------------------------------------------------


def _centerpiece_mark(start_ms: int) -> str:
    """Mark the motion anchor AND give it a scene-relative start delay.

    Motions are CSS animations on descendants, and a CSS ``animation-delay``
    is measured from when the element is rendered -- not from when its scene
    starts. Without the offset, thinking-pulse plays its full PULSE_MS at page
    load and is long finished before a scene starting at 5s is ever on
    screen. The motion grammar only ever worked on scene 1 because scene 1
    starts at 0, where the two coincide.
    """
    return f' data-centerpiece style="animation-delay:{start_ms}ms"'


def _title(
    scene: Scene,
    spec: VideoSpec,
    centerpiece: bool = False,
    start_ms: int = 0,
) -> str:
    """Render the title claim as an ``<h1>``.

    ``centerpiece`` marks this element as THE single element a motion should
    animate. Motions need exactly one target and the renderer — not CSS — is
    the only thing that knows which element that is. On quote-card the title
    is the small attribution line while the quote glyph is the visual anchor;
    a bare ``.glyph, h1`` selector would have pulsed both. Marking it in the
    markup keeps the motion deterministic and independent of CSS feature
    support (no reliance on ``:has()``).
    """
    claim = spec.claim(scene.title_claim_id)
    text = claim.text if claim else ""
    cid = claim.claim_id if claim else ""
    mark = _centerpiece_mark(start_ms) if centerpiece else ""
    if scene.motion == "word-sweep":
        return (
            f'<h1 data-claim-id="{_esc(cid)}" data-motion="word-sweep"{mark}>'
            f"{_word_sweep_spans(text, start_ms=start_ms)}</h1>"
        )
    return f'<h1 data-claim-id="{_esc(cid)}"{mark}>{_esc(text)}</h1>'


def _word_sweep_spans(
    text: str,
    *,
    start_ms: int = 0,
    per_word_ms: int = WORD_STAGGER_MS,
    duration_ms: int = WORD_TRAVEL_MS,
) -> str:
    """Wrap each word in a span with a staggered animation-delay.

    Pure function of word index and scene start: delay = start_ms +
    i * per_word_ms. ``start_ms`` is mandatory in spirit — a delay measured
    from page load rather than from the scene's own start finishes before any
    scene but the first is on screen.

    The CSS keyframe animates transform only (translateY 8px -> none) — no
    opacity on the children, because the scene body's fade-rise already
    animates opacity and stacking fractional opacities would drop the
    subtree.

    The whole-sweep total is (n_words - 1) * per_word_ms + duration_ms.
    For 7 words at the defaults: 600 + 480 = 1080 ms. Travel is 16px over
    WORD_TRAVEL_MS, which clears the 1px/frame pixel-velocity floor at the
    project default of 30fps.
    """
    words = (text or "").split()
    out: list[str] = []
    for i, w in enumerate(words):
        delay = start_ms + i * per_word_ms
        out.append(
            f'<span class="word" '
            f'style="animation-delay:{delay}ms;animation-duration:{duration_ms}ms">'
            f"{_esc(w)}</span>"
        )
    return " ".join(out)


def _narration(scene: Scene, spec: VideoSpec, cls: str = "") -> str:
    claim = spec.claim(scene.narration_claim_id)
    if claim is None:
        return ""
    attr = f' class="{cls}"' if cls else ""
    return f'<p{attr} data-claim-id="{_esc(claim.claim_id)}">{_esc(claim.text)}</p>'


def _narration_text(scene: Scene, spec: VideoSpec) -> str:
    claim = spec.claim(scene.narration_claim_id)
    return claim.text if claim else ""


def _title_text(scene: Scene, spec: VideoSpec) -> str:
    claim = spec.claim(scene.title_claim_id)
    return claim.text if claim else ""


def _rows(items: list[str], marker: str = "dot") -> str:
    out = []
    for item in items:
        mark = '<span class="dot"></span>' if marker == "dot" else f'<span class="mono accent">{_esc(marker)}</span>'
        out.append(f'<div class="row">{mark}<span>{_esc(item)}</span></div>')
    return f'<div class="rows">{"".join(out)}</div>'


def _body(scene: Scene, spec: VideoSpec, start_ms: int = 0) -> str:
    """Render one scene's foreground according to its treatment.

    ``start_ms`` is the scene's own start time. Every descendant motion is
    offset by it, because a CSS animation-delay runs from element render, not
    from scene start.

    Every branch derives its content by *splitting* the bound claims. Nothing
    here is allowed to author new copy, which is what makes
    ``unbound_visible_number`` structurally impossible rather than merely
    checked-for afterwards.
    """
    treatment = scene.treatment
    # The title is the centerpiece for every treatment except quote-card,
    # where the quote glyph is the visual anchor and the title is only the
    # small attribution line beneath it.
    title = _title(scene, spec, centerpiece=True, start_ms=start_ms)
    narration = _narration_text(scene, spec)
    clauses = _split_clauses(narration)

    if treatment == "hero-centered":
        return f"{title}{_narration(scene, spec)}"

    if treatment == "hero-split":
        return f'<div>{title}</div><div class="side">{_narration(scene, spec)}</div>'

    if treatment in ("statement-left", "statement-right", "rebuttal-right"):
        return (
            f'<div class="vrule"></div>'
            f'<div class="body">{title}{_narration(scene, spec)}</div>'
        )

    if treatment == "feature-rows":
        return f"{title}{_rows(clauses)}"

    if treatment == "ui-frame":
        chrome = '<div class="chrome"><i></i><i></i><i></i></div>'
        return (
            f'{title}<div class="frame">{chrome}'
            f'{_rows(clauses, marker="›")}</div>'
        )

    if treatment == "compare-columns":
        left = clauses[0] if clauses else ""
        right = ". ".join(_split_sentences(" ".join(clauses[1:]))) if len(clauses) > 1 else narration
        return (
            f'{title}<div class="cols">'
            f'<div class="col"><p data-claim-id="{_esc(scene.narration_claim_id or "")}">{_esc(left)}</p></div>'
            f'<div class="col lead"><p data-claim-id="{_esc(scene.narration_claim_id or "")}">{_esc(right)}</p></div>'
            f"</div>"
        )

    if treatment == "quote-card":
        # The glyph is the anchor here, not the title. _body's shared `title`
        # is built with centerpiece=True, so re-render it without the marker
        # and stamp the glyph instead — otherwise a pulse would hit both the
        # big quote mark and the small attribution line.
        return (
            f'<div class="glyph"{_centerpiece_mark(start_ms)}>&ldquo;</div>'
            f'<blockquote data-claim-id="{_esc(scene.narration_claim_id or "")}">{_esc(narration)}</blockquote>'
            f'<div class="attr">{_title(scene, spec, start_ms=start_ms)}</div>'
        )

    if treatment == "stat-hero":
        # The figure is the TITLE's numeral. An author sets the title claim to
        # e.g. "40%" and the narration supplies the supporting line. Reading the
        # figure out of the narration instead put the narration's number in
        # .figure AND the title's number in the h1 underneath — two huge numbers
        # in one frame, and the wrong one was the big one. Nothing but the
        # layout contact sheet could have caught this; every QA stage passed.
        #
        # Whichever claim carries the numeral, the TITLE claim still has to be
        # rendered as an <h1>. When the title is the figure, the figure IS the
        # h1. claim_grounding reports title_missing for the scene otherwise.
        title_text = _title_text(scene, spec)
        from_title = _stat_token(title_text) is not None
        figure_source = title_text if from_title else narration
        token = _stat_token(figure_source)
        if token is None:
            # precondition should have blocked this; never invent a figure
            return (
                f'<div class="glyph">&ldquo;</div>'
                f'<blockquote data-claim-id="{_esc(scene.narration_claim_id or "")}">{_esc(narration)}</blockquote>'
                f'<div class="attr">{title}</div>'
            )
        label = _stat_label(figure_source, token)
        caption = f'<div class="caption">{_esc(label)}</div>' if label else ""
        if from_title:
            figure = (
                f'<h1 class="figure"{_centerpiece_mark(start_ms)} '
                f'data-claim-id="{_esc(scene.title_claim_id or "")}">'
                f"{_esc(token)}</h1>"
            )
            support_line = (
                f'<p data-claim-id="{_esc(scene.narration_claim_id or "")}">{_esc(narration)}</p>'
                if narration
                else ""
            )
        else:
            figure = (
                f'<div class="figure"{_centerpiece_mark(start_ms)} '
                f'data-claim-id="{_esc(scene.narration_claim_id or "")}">'
                f"{_esc(token)}</div>"
            )
            support_line = (
                f'<h1 data-claim-id="{_esc(scene.title_claim_id or "")}">{_esc(title_text)}</h1>'
                if title_text
                else ""
            )
        return f"{figure}{caption}{support_line}"

    if treatment == "cta-command":
        lines = "".join(
            f'<div class="line"><span class="prompt">&gt;</span>'
            f'<span data-claim-id="{_esc(scene.narration_claim_id or "")}">{_esc(c)}</span></div>'
            for c in clauses
        )
        return f'{title}<div class="lines">{lines}</div>'

    if treatment == "cta-panel":
        return f'<div class="panel">{title}{_narration(scene, spec)}</div>'

    # unknown treatment: fall back to the plainest possible statement
    return f"{title}{_narration(scene, spec)}"


# --------------------------------------------------------------------------
# document
# --------------------------------------------------------------------------


def _stylesheet(spec: VideoSpec) -> str:
    brand_css = to_css(spec.brand) if spec.brand else ":root{--bg:#0B0B0D;--fg:#F5F5F7}"
    base = _BASE_CSS.replace("OPACITY_FLOOR", str(OPACITY_FLOOR)).replace(
        "PULSE_MS", str(PULSE_MS)
    )

    used = {s.treatment for s in spec.scenes}
    blocks = "".join(_TREATMENT_CSS.get(t, "") for t in sorted(used))

    # Substitute over the *combined* stylesheet, not per block. Substituting
    # only the base left literal "SANS"/"MONO" in every treatment rule; the
    # HyperFrames linter reads those as two undeclared font families and
    # hard-fails the render under --strict.
    css = (base + blocks).replace("SANS", _SANS_STACK).replace("MONO", _MONO_STACK)
    return f"{_font_faces()}\n{brand_css}\n{css}"


def _surface_style(spec: VideoSpec) -> str:
    """Inline background for any surface the ancestor-walking audit inspects.

    The static canvas audit is a text check on the element's own tag, so a
    background supplied by the stylesheet's ``.clip`` rule is invisible to it.
    Declaring it inline satisfies both that audit and HyperFrames' runtime
    check, and removes any dependence on CSS variable resolution.
    """
    return f"background:{spec.canvas.background};background-image:none"


def _clip(scene: Scene, spec: VideoSpec, window: SceneWindow, index: int) -> str:
    start_ms = _offset_ms(window)
    body = _body(scene, spec, start_ms=start_ms)

    # delay/duration carry one entry per animation declared in .clip-motion:
    # the entrance, then the invisible hold that fixes the composition length.
    inner = (
        f'<div class="scene-body clip-motion" '
        f'style="animation-delay:{window.start_s}s,{window.start_s}s;'
        f'animation-duration:{_entrance_ms(spec)}ms,{scene.duration_s}s">{body}</div>'
    )

    narration_src = ""
    for aid in scene.asset_ids:
        asset = spec.asset(aid)
        if asset and asset.kind == "audio":
            narration_src = f' data-narration="{_esc(asset.path)}"'
            break

    return (
        f'<section id="{_esc(scene.scene_id)}" '
        f'class="clip t-{_esc(scene.treatment)} m-{_esc(scene.motion)}" '
        f'data-start="{window.start_s}" data-duration="{scene.duration_s}" '
        f'data-track-index="{index}" data-no-timeline '
        f'data-treatment="{_esc(scene.treatment)}" '
        f'data-motion="{_esc(scene.motion)}" '
        f'data-role="{_esc(scene.role)}" style="{_surface_style(spec)}"'
        f"{narration_src}>{inner}</section>"
    )


def render_document(spec: VideoSpec, plan: TimelinePlan) -> str:
    """Build the full HyperFrames HTML document."""
    clips = []
    for i, scene in enumerate(spec.scenes):
        window = plan.window(scene.scene_id)
        if window is None:
            raise ValueError(f"scene {scene.scene_id} has no timeline window")
        clips.append(_clip(scene, spec, window, i))

    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{_esc(spec.title or spec.spec_id)}</title>\n"
        f"<style>\n{_stylesheet(spec)}\n</style>\n"
        "</head>\n<body>\n"
        # The runtime reads geometry and playback start from data- attributes,
        # not from CSS: without data-width/data-height the root has no
        # dimensions, and without data-start="0" it never begins playback.
        # data-no-timeline skips the 45s poll for a window.__timelines
        # registration we deliberately do not make.
        f'<div data-composition-id="{_esc(spec.spec_id)}" '
        f'data-width="{spec.canvas.width}" data-height="{spec.canvas.height}" '
        f'data-start="0" data-no-timeline '
        f'style="{_surface_style(spec)};'
        f'width:{spec.canvas.width}px;height:{spec.canvas.height}px">\n'
        + "\n".join(clips)
        + "\n</div>\n</body>\n</html>\n"
    )


def scene_fragments(spec: VideoSpec, plan: TimelinePlan) -> dict[str, str]:
    """Markup for one scene, for QA to ground-check without rendering."""
    out: dict[str, str] = {}
    for i, scene in enumerate(spec.scenes):
        window = plan.window(scene.scene_id)
        if window is None:
            continue
        out[scene.scene_id] = _clip(scene, spec, window, i)
    return out


def write_project(spec: VideoSpec, plan: TimelinePlan, project_dir: Path) -> tuple[Path, dict[str, str]]:
    project_dir.mkdir(parents=True, exist_ok=True)
    entry = project_dir / "index.html"
    entry.write_text(render_document(spec, plan), encoding="utf-8")
    return entry, scene_fragments(spec, plan)
