"""Shared spec fixtures.

The builder is deliberately explicit about every schema key. A fixture that
relies on defaults would quietly pass validation tests that are supposed to be
checking required fields, and would not notice if the schema grew a key.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from colophon.spec.schema import VideoSpec

FPS = 30


def scene(
    scene_id: str,
    role: str = "hook",
    treatment: str = "hero-centered",
    duration_s: float = 2.0,
    title: str | None = "t1",
    narration: str | None = "n1",
    **overrides: Any,
) -> dict[str, Any]:
    payload = {
        "scene_id": scene_id,
        "role": role,
        "treatment": treatment,
        "duration_s": duration_s,
        "title_claim_id": title,
        "narration_claim_id": narration,
        "asset_ids": [],
        "treatment_params": {},
        "renderer_hints": {},
    }
    payload.update(overrides)
    return payload


def spec_dict(**overrides: Any) -> dict[str, Any]:
    """A minimal spec that passes ``validate`` with no problems."""
    spec: dict[str, Any] = {
        "spec_version": "0.1",
        "spec_id": "test-spec",
        "title": "Test launch",
        "canvas": {
            "width": 1920,
            "height": 1080,
            "fps": FPS,
            "background": "#0B0B12",
        },
        "brand": {
            "name": "Testco",
            "tokens": {"bg": "#0B0B12", "fg": "#F5F5F7", "accent": "#4F8CFF"},
            "voice": {},
        },
        "timeline": {
            "policy": "adjacent",
            "overlap_s": 0.0,
            "transition": "cut",
            "transition_ms": 0,
        },
        "assets": [],
        "claims": [
            {
                "claim_id": "t1",
                "text": "Ship faster",
                "kind": "title",
                "source": "brief#positioning",
            },
            {
                "claim_id": "n1",
                "text": "Teams ship faster, with fewer regressions.",
                "kind": "narration",
                "source": "brief#problem",
            },
        ],
        "scenes": [scene("s1")],
        "notes": "",
    }
    for key, value in overrides.items():
        spec[key] = value
    return spec


def two_scene_spec(**overrides: Any) -> dict[str, Any]:
    """Two scenes, each with its own claim pair.

    Every claim must be referenced by some scene or ``validate`` reports it as
    dead weight, so the second scene brings its own claims rather than reusing
    the first scene's.
    """
    raw = spec_dict(
        claims=[
            {
                "claim_id": "t1",
                "text": "Ship faster",
                "kind": "title",
                "source": "brief#positioning",
            },
            {
                "claim_id": "n1",
                "text": "Teams ship faster, with fewer regressions.",
                "kind": "narration",
                "source": "brief#problem",
            },
            {
                "claim_id": "t2",
                "text": "Built for engineers",
                "kind": "title",
                "source": "brief#audience",
            },
            {
                "claim_id": "n2",
                "text": "Every run is hashed, every attempt is reproducible.",
                "kind": "narration",
                "source": "brief#capability",
            },
        ],
        scenes=[scene("s1"), scene("s2", role="capability", treatment="feature-rows", title="t2", narration="n2")],
    )
    for key, value in overrides.items():
        raw[key] = value
    return raw


@pytest.fixture
def make_spec():
    """Return a factory producing a fresh, independent spec dict."""

    def _make(**overrides: Any) -> dict[str, Any]:
        return copy.deepcopy(spec_dict(**overrides))

    return _make


@pytest.fixture
def valid_spec() -> VideoSpec:
    return VideoSpec.from_dict(spec_dict())
