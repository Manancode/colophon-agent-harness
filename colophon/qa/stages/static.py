"""Static checks on the emitted project — no browser, no render.

These are cheap enough to run on every attempt and catch the failures that
would otherwise cost a full render to discover.
"""

from __future__ import annotations

import re
from typing import Any

from ...spec.schema import VideoSpec
from ..runner import StageResult

_DUPLICATE_ATTR_RE = re.compile(r"<[a-zA-Z][^>]*?\s([a-zA-Z-]+)=[^\s>]+(?:\s[^>]*?\s\1=)", re.S)
_EVENT_HANDLER_RE = re.compile(r"\son[a-z]+\s*=", re.I)
_REMOTE_RE = re.compile(r"(?:src|href)\s*=\s*[\"'](https?:)?//", re.I)
_UNSAFE_RE = re.compile(r"<(iframe|object|embed)\b", re.I)
_FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}\"]+)", re.I)
_FONT_FACE_RE = re.compile(r"@font-face", re.I)

#: Families the linter accepts without an @font-face because they are keywords
#: or generic families rather than named fonts.
_GENERIC_FAMILIES = frozenset(
    {"inherit", "initial", "unset", "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui"}
)


def static_html(
    spec: VideoSpec, *, document: str | None = None, **_: Any
) -> StageResult:
    problems: list[str] = []
    if not document:
        return StageResult(
            stage_id="static_html",
            passed=False,
            problems=["no emitted document to check"],
        )

    for m in _DUPLICATE_ATTR_RE.finditer(document):
        problems.append(f"duplicate attribute {m.group(1)!r} on an element")

    for m in _EVENT_HANDLER_RE.finditer(document):
        problems.append(f"inline event handler {m.group(0)!r} is not allowed")

    for m in _REMOTE_RE.finditer(document):
        problems.append(f"remote reference {m.group(0)!r}; assets must be local")

    for m in _UNSAFE_RE.finditer(document):
        problems.append(f"unsafe embedded content <{m.group(1)}>")

    problems.extend(_font_face_problems(document))

    return StageResult(
        stage_id="static_html",
        passed=not problems,
        problems=problems,
        detail={"document_bytes": len(document)},
    )


def _font_face_problems(document: str) -> list[str]:
    """Every named font family needs an @font-face with a local() source.

    HyperFrames hard-rejects ``font_family_without_font_face``. The remedy is
    ``@font-face { src: local('Exact Font Name') }`` for OS-bundled fonts,
    which keeps the render offline and deterministic.
    """
    declared = set()
    for block in _FONT_FACE_RE.split(document)[1:]:
        for m in re.finditer(r"font-family\s*:\s*['\"]?([^;}\"']+)", block[:400], re.I):
            declared.add(m.group(1).strip().strip("'\"").lower())

    used: set[str] = set()
    for m in _FONT_FAMILY_RE.finditer(document):
        for raw in m.group(1).split(","):
            name = raw.strip().strip("'\"").strip().lower()
            if not name or name in _GENERIC_FAMILIES:
                continue
            used.add(name)

    missing = sorted(used - declared)
    return [
        f"font family {name!r} used without an @font-face declaration"
        for name in missing
    ]


def canvas_audit(
    spec: VideoSpec, *, document: str | None = None, **_: Any
) -> StageResult:
    """The composition root and every clip must carry the brand background.

    The audit that matters downstream walks *ancestors only*, so a clip whose
    own background is wrong cannot be rescued by its parent. Descendants are
    unconstrained — that is where all legitimate visual variation lives, and it
    is the reason treatments can paint freely inside a scene.
    """
    problems: list[str] = []
    if not document:
        return StageResult(
            stage_id="canvas_audit", passed=False, problems=["no emitted document"]
        )

    bg = spec.canvas.background
    expected = f"background:{bg}"

    root = re.search(r"<div[^>]*data-composition-id[^>]*>", document)
    if not root:
        problems.append("no data-composition-id root found")
    else:
        problems.extend(_check_surface(root.group(0), bg, expected, "composition root"))

    for m in re.finditer(r"<section[^>]*class=\"[^\"]*\bclip\b[^\"]*\"[^>]*>", document):
        scene_id = re.search(r'id="([^"]+)"', m.group(0))
        label = scene_id.group(1) if scene_id else "clip"
        problems.extend(_check_surface(m.group(0), bg, expected, label))

    return StageResult(
        stage_id="canvas_audit",
        passed=not problems,
        problems=problems,
        detail={"expected_background": bg},
    )


def _check_surface(tag: str, bg: str, expected: str, label: str) -> list[str]:
    """The audit walks ancestors, so it inspects only the element's own style."""
    problems: list[str] = []
    style = re.search(r'style="([^"]*)"', tag)
    inline = style.group(1) if style else ""
    blob = (tag + " " + inline).lower()

    if expected.lower().replace(":", ":") not in blob.replace(" ", ""):
        # the background may also arrive via the stylesheet's .clip rule
        if f"background:{bg}".lower() not in blob.replace(" ", ""):
            problems.append(
                f"{label}: inline background is not the brand colour {bg!r}"
            )
    if "background-image" in blob and "background-image:none" not in blob.replace(" ", ""):
        problems.append(f"{label}: background-image must be none")
    return problems
