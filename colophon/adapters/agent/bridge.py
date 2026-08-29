"""Agent bridge — optional, thin, and never imported by the core.

The rule: Colophon must run to completion with this file deleted. Any agent
runtime can drive Colophon through the CLI or through these two translation
functions, but nothing in ``colophon/spec``, ``colophon/qa``,
``colophon/renderers`` or anywhere else may import from here.

What that buys us: the pipeline stays testable and reproducible on its own,
and an agent runtime is a caller rather than a dependency.
"""

from __future__ import annotations

from typing import Any

from ...spec.io import dumps
from ...spec.schema import VideoSpec


def spec_to_payload(spec: VideoSpec) -> dict[str, Any]:
    """A compact, model-friendly projection of the spec.

    Deliberately lossy in one direction only: it adds nothing. Every string an
    agent sees here is already in the spec, so an agent cannot treat generated
    commentary as if it were grounded content.
    """
    claims = {c.claim_id: c.text for c in spec.claims}
    return {
        "product": spec.brand.name if spec.brand else None,
        "title": spec.title,
        "canvas": spec.canvas.to_dict(),
        "scenes": [
            {
                "scene_id": s.scene_id,
                "role": s.role,
                "treatment": s.treatment,
                "duration_s": s.duration_s,
                "title": claims.get(s.title_claim_id or ""),
                "narration": claims.get(s.narration_claim_id or ""),
            }
            for s in spec.scenes
        ],
        "claims": [
            {"claim_id": c.claim_id, "text": c.text, "kind": c.kind, "source": c.source}
            for c in spec.claims
        ],
    }


def spec_to_prompt_context(spec: VideoSpec) -> str:
    """Render the spec as text to paste into a prompt."""
    payload = spec_to_payload(spec)
    lines = [
        f"Product: {payload['product']}",
        f"Resolution: {spec.canvas.width}x{spec.canvas.height} @ {spec.canvas.fps}fps",
        "",
        "Scenes:",
    ]
    for s in payload["scenes"]:
        lines.append(
            f"  - {s['scene_id']} [{s['role']}/{s['treatment']}] {s['duration_s']}s"
        )
        if s["title"]:
            lines.append(f"      title:     {s['title']}")
        if s["narration"]:
            lines.append(f"      narration: {s['narration']}")
    lines += ["", "Grounded claims (these are the only permitted sources of copy):"]
    for c in payload["claims"]:
        src = f" ({c['source']})" if c["source"] else ""
        lines.append(f"  - {c['claim_id']} [{c['kind']}]{src}: {c['text']}")
    return "\n".join(lines)


def qa_problems_to_patch_hints(problems: list[str]) -> list[dict[str, str]]:
    """Turn QA failures into suggested repair targets.

    Suggestions only. The repair step validates every op against the schema,
    so a bad hint fails loudly rather than quietly mutating the spec.
    """
    hints: list[dict[str, str]] = []
    for problem in problems:
        if problem.startswith("[claim_grounding]"):
            hints.append({"kind": "grounding", "detail": problem})
        elif problem.startswith("[static_html]"):
            hints.append({"kind": "markup", "detail": problem})
        elif problem.startswith("[canvas_audit]"):
            hints.append({"kind": "canvas", "detail": problem})
        elif problem.startswith("[media_contract]"):
            hints.append({"kind": "media", "detail": problem})
        else:
            hints.append({"kind": "other", "detail": problem})
    return hints


def spec_fingerprint_for_logging(spec: VideoSpec) -> str:
    from ...spec.hash import spec_sha256

    return spec_sha256(spec)[:12]


def spec_json(spec: VideoSpec) -> str:
    return dumps(spec)
