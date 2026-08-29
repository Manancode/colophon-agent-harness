"""Canonical scene roles.

A role says *what the scene is for*. It is renderer-agnostic and
treatment-agnostic. The treatment says *how it looks*.

Keeping these apart is what stops the system from degenerating into "six
slides that happen to have different words in them" — the failure mode we
diagnosed in an early cut of a launch video built with this system.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    role_id: str
    intent: str
    #: scenes with this role normally appear at these positions
    typical_index: tuple[int, ...] = ()


ROLES: dict[str, Role] = {
    r.role_id: r
    for r in (
        Role(
            "hook",
            "Earn the next ten seconds. Name the product and the change it makes.",
            (0,),
        ),
        Role(
            "problem",
            "Name the pain the viewer already has, in their words.",
            (1,),
        ),
        Role(
            "capability",
            "Show the mechanism. What the product actually does.",
            (2, 3),
        ),
        Role(
            "differentiator",
            "Say why this and not the thing they use today.",
            (3, 4),
        ),
        Role(
            "proof",
            "Evidence: a number, a quote, an outcome.",
            (4, 5),
        ),
        Role(
            "cta",
            "One action, stated once, unmistakably.",
            (5, 6),
        ),
    )
}


def role_ids() -> tuple[str, ...]:
    return tuple(ROLES)


def describe(role_id: str) -> str:
    role = ROLES.get(role_id)
    return role.intent if role else "(unknown role)"


def check_narrative_order(scene_roles: list[str]) -> list[str]:
    """Warn about structurally odd running orders.

    Advisory, not fatal — some launches legitimately open on the problem. But
    a video that opens on the CTA is almost always a planning bug, and it is
    cheaper to say so than to render it.
    """
    problems: list[str] = []
    if not scene_roles:
        return ["no scenes"]

    if scene_roles[0] == "cta":
        problems.append("first scene has role 'cta'")
    if scene_roles[-1] != "cta":
        problems.append(f"last scene has role {scene_roles[-1]!r}; expected 'cta'")
    if "hook" not in scene_roles:
        problems.append("no scene has role 'hook'")

    first_proof = scene_roles.index("proof") if "proof" in scene_roles else -1
    first_cap = scene_roles.index("capability") if "capability" in scene_roles else -1
    if first_proof >= 0 and first_cap >= 0 and first_proof < first_cap:
        problems.append("proof appears before capability; evidence precedes mechanism")

    return problems
