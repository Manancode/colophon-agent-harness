"""Canonical video spec — the single source of truth for a Colophon run.

Design rules that shaped this file:

1. Time is authored in SECONDS. Frames are a renderer concern. Storing
   startFrame/durationInFrames lets an fps change silently rewrite the whole
   timeline.
2. No renderer-specific keys. Nothing here mentions HTML or CSS. Renderer
   knobs live in ``Scene.renderer_hints``, which is advisory and never
   authoritative.
3. No inlined content. Embedding app markup in clip props is how a spec file
   grows to megabytes. Here assets are referenced by path + sha256 and copy
   is referenced by claim id.
4. Frozen dataclasses. The spec is a value; mutating it makes a new spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

SPEC_VERSION = "0.1"

#: Scene roles. Closed set — a spec cannot invent a role.
ROLES: tuple[str, ...] = (
    "hook",
    "problem",
    "capability",
    "differentiator",
    "proof",
    "cta",
)


class SpecError(ValueError):
    """Raised when a spec is structurally or semantically invalid."""


# --------------------------------------------------------------------------
# value types
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Canvas:
    """Output geometry and clock. Maps 1:1 onto a rendered composition."""

    width: int = 1920
    height: int = 1080
    fps: int = 30
    background: str = "#0B0B0D"

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "background": self.background,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Canvas":
        return cls(
            width=int(d["width"]),
            height=int(d["height"]),
            fps=int(d["fps"]),
            background=str(d["background"]),
        )


@dataclass(frozen=True)
class Brand:
    """Brand identity. ``tokens`` is the contract with the renderer: the
    adapter must expose each key as a CSS custom property / theme value."""

    name: str
    tokens: dict[str, str] = field(default_factory=dict)
    voice: dict[str, Any] = field(default_factory=dict)

    REQUIRED_TOKENS: tuple[str, ...] = ("bg", "fg", "accent")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "tokens": dict(self.tokens), "voice": dict(self.voice)}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Brand":
        return cls(
            name=str(d["name"]),
            tokens=dict(d.get("tokens") or {}),
            voice=dict(d.get("voice") or {}),
        )


@dataclass(frozen=True)
class Asset:
    """A local, content-addressed input. No remote URLs are permitted."""

    asset_id: str
    kind: str  # image | audio | video | font | data
    path: str
    sha256: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    KINDS: tuple[str, ...] = ("image", "audio", "video", "font", "data")

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "kind": self.kind,
            "path": self.path,
            "sha256": self.sha256,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Asset":
        return cls(
            asset_id=str(d["asset_id"]),
            kind=str(d.get("kind") or "image"),
            path=str(d["path"]),
            sha256=str(d.get("sha256") or ""),
            meta=dict(d.get("meta") or {}),
        )


@dataclass(frozen=True)
class Claim:
    """One grounded statement. Every visible string resolves to a claim.

    ``kind`` drives which treatments may bind it:
      - ``title``      short headline
      - ``narration``  spoken / body copy
      - ``stat``       contains a measurable number
      - ``quote``      attributed testimonial
    """

    claim_id: str
    text: str
    kind: str = "narration"
    source: str = ""

    KINDS: tuple[str, ...] = ("title", "narration", "stat", "quote")

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "kind": self.kind,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Claim":
        return cls(
            claim_id=str(d["claim_id"]),
            text=str(d["text"]),
            kind=str(d.get("kind") or "narration"),
            source=str(d.get("source") or ""),
        )


@dataclass(frozen=True)
class Scene:
    """One beat of the video.

    ``duration_s`` is the only timing input. Starts are computed by the
    timeline layer according to ``VideoSpec.timeline.policy``, so a scene can
    never drift out of alignment with its neighbours.
    """

    scene_id: str
    role: str
    treatment: str
    duration_s: float
    motion: str = "fade-rise"
    title_claim_id: str | None = None
    narration_claim_id: str | None = None
    asset_ids: tuple[str, ...] = ()
    treatment_params: dict[str, Any] = field(default_factory=dict)
    renderer_hints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "role": self.role,
            "treatment": self.treatment,
            "duration_s": self.duration_s,
            "motion": self.motion,
            "title_claim_id": self.title_claim_id,
            "narration_claim_id": self.narration_claim_id,
            "asset_ids": list(self.asset_ids),
            "treatment_params": dict(self.treatment_params),
            "renderer_hints": dict(self.renderer_hints),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Scene":
        return cls(
            scene_id=str(d["scene_id"]),
            role=str(d["role"]),
            treatment=str(d["treatment"]),
            duration_s=float(d["duration_s"]),
            motion=str(d.get("motion") or "fade-rise"),
            title_claim_id=d.get("title_claim_id"),
            narration_claim_id=d.get("narration_claim_id"),
            asset_ids=tuple(str(a) for a in (d.get("asset_ids") or ())),
            treatment_params=dict(d.get("treatment_params") or {}),
            renderer_hints=dict(d.get("renderer_hints") or {}),
        )


@dataclass(frozen=True)
class Timeline:
    """How scenes are laid onto the clock.

    ``adjacent``  starts are derived from durations and ``overlap_s``, so
                  scenes can never drift apart.
    ``explicit``  each scene carries its own start (not supported in V0).

    ``overlap_s`` exists because real launch videos overlap their scenes. In
    a launch document that actually shipped, all five scene boundaries
    overlapped by 6-12 frames, each carrying a ``matchCut`` transition. A strictly-adjacent timeline cannot express that, so V0
    supports a uniform overlap rather than pretending cuts are the only
    transition.

    There is deliberately no ``playback_speed``. We have seen a document carry
    ``playbackSpeed: 1.25``, which silently turned its advertised 22.3s into
    an actual 17.9s — a global time transform nobody could see at the scene
    level. Speed belongs in a scene's own timing, never as a document-wide
    multiplier.
    """

    policy: str = "adjacent"
    overlap_s: float = 0.0
    transition: str = "cut"
    transition_ms: int = 400

    POLICIES: tuple[str, ...] = ("adjacent", "explicit")
    TRANSITIONS: tuple[str, ...] = ("cut", "match_cut", "fade")

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "overlap_s": self.overlap_s,
            "transition": self.transition,
            "transition_ms": self.transition_ms,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Timeline":
        return cls(
            policy=str(d.get("policy") or "adjacent"),
            overlap_s=float(d.get("overlap_s") or 0.0),
            transition=str(d.get("transition") or "cut"),
            transition_ms=int(d.get("transition_ms") or 0),
        )


@dataclass(frozen=True)
class VideoSpec:
    """The canonical, renderer-agnostic description of one launch video."""

    spec_id: str
    title: str
    canvas: Canvas = field(default_factory=Canvas)
    brand: Brand | None = None
    timeline: Timeline = field(default_factory=Timeline)
    assets: tuple[Asset, ...] = ()
    claims: tuple[Claim, ...] = ()
    scenes: tuple[Scene, ...] = ()
    spec_version: str = SPEC_VERSION
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_version": self.spec_version,
            "spec_id": self.spec_id,
            "title": self.title,
            "canvas": self.canvas.to_dict(),
            "brand": self.brand.to_dict() if self.brand else None,
            "timeline": self.timeline.to_dict(),
            "assets": [a.to_dict() for a in self.assets],
            "claims": [c.to_dict() for c in self.claims],
            "scenes": [s.to_dict() for s in self.scenes],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "VideoSpec":
        version = str(d.get("spec_version") or SPEC_VERSION)
        if version != SPEC_VERSION:
            raise SpecError(f"unsupported spec_version {version!r}; expected {SPEC_VERSION!r}")
        brand = d.get("brand")
        return cls(
            spec_id=str(d["spec_id"]),
            title=str(d.get("title") or ""),
            canvas=Canvas.from_dict(d["canvas"]) if "canvas" in d else Canvas(),
            brand=Brand.from_dict(brand) if brand else None,
            timeline=Timeline.from_dict(d["timeline"]) if "timeline" in d else Timeline(),
            assets=tuple(Asset.from_dict(a) for a in (d.get("assets") or ())),
            claims=tuple(Claim.from_dict(c) for c in (d.get("claims") or ())),
            scenes=tuple(Scene.from_dict(s) for s in (d.get("scenes") or ())),
            spec_version=version,
            notes=str(d.get("notes") or ""),
        )

    # -- convenience -------------------------------------------------------

    @property
    def total_duration_s(self) -> float:
        return round(sum(s.duration_s for s in self.scenes), 6)

    def claim(self, claim_id: str | None) -> Claim | None:
        if claim_id is None:
            return None
        for c in self.claims:
            if c.claim_id == claim_id:
                return c
        return None

    def asset(self, asset_id: str) -> Asset | None:
        for a in self.assets:
            if a.asset_id == asset_id:
                return a
        return None
