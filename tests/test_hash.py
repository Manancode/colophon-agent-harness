"""Spec hashing and scene-locality proofs.

Locality is the property that makes targeted repair trustworthy: after editing
one scene, only that scene's hash may change. If unrelated scenes move, the
edit was not local, and a partial re-render would be unsound. Repair measures
this even though V0 still re-renders everything.
"""

from __future__ import annotations

import pytest

from colophon.spec.hash import (
    diff_scene_hashes,
    scene_hashes,
    scene_sha256,
    sha256_obj,
    spec_sha256,
)
from colophon.spec.io import canonical_bytes
from colophon.spec.schema import VideoSpec

from .conftest import two_scene_spec


def _build(**overrides) -> VideoSpec:
    return VideoSpec.from_dict(two_scene_spec(**overrides))


class TestCanonicalBytes:
    def test_key_order_does_not_change_the_hash(self):
        assert sha256_obj({"a": 1, "b": 2}) == sha256_obj({"b": 2, "a": 1})

    def test_nested_key_order_does_not_change_the_hash(self):
        left = {"x": {"a": 1, "b": 2}, "y": [1, 2]}
        right = {"y": [1, 2], "x": {"b": 2, "a": 1}}
        assert sha256_obj(left) == sha256_obj(right)

    def test_non_ascii_is_not_escaped(self):
        # ensure_ascii=False keeps the bytes stable and human-inspectable
        assert "é".encode("utf-8") in canonical_bytes({"k": "é"})

    def test_compact_separators(self):
        assert canonical_bytes({"a": 1}) == b'{"a":1}'


class TestSpecSha256:
    def test_is_deterministic(self):
        assert spec_sha256(_build()) == spec_sha256(_build())

    def test_changes_when_content_changes(self):
        before = _build()
        raw = two_scene_spec()
        raw["claims"][0]["text"] = "Ship much faster"
        assert spec_sha256(before) != spec_sha256(VideoSpec.from_dict(raw))


class TestSceneLocality:
    def test_editing_one_scene_leaves_the_others_unchanged(self):
        before = _build()
        raw = two_scene_spec()
        raw["scenes"][1]["duration_s"] = 9.0
        after = VideoSpec.from_dict(raw)

        diff = diff_scene_hashes(scene_hashes(before), scene_hashes(after))
        assert diff["changed"] == ["s2"]
        assert diff["unchanged"] == ["s1"]
        assert diff["added"] == []
        assert diff["removed"] == []

    def test_editing_a_claim_only_moves_the_scene_that_binds_it(self):
        before = _build()
        raw = two_scene_spec()
        # n2 is bound only by s2
        raw["claims"][3]["text"] = "Every run is hashed, every attempt is auditable."
        after = VideoSpec.from_dict(raw)

        diff = diff_scene_hashes(scene_hashes(before), scene_hashes(after))
        assert diff["changed"] == ["s2"]

    def test_adding_a_scene_adds_exactly_one_hash(self):
        from .conftest import scene

        before = _build()
        raw = two_scene_spec()
        raw["scenes"].append(scene("s3", role="cta", treatment="cta-panel", title="t1", narration="n1"))
        after = VideoSpec.from_dict(raw)

        diff = diff_scene_hashes(scene_hashes(before), scene_hashes(after))
        assert diff["added"] == ["s3"]
        assert diff["changed"] == []

    def test_scene_hash_covers_canvas(self):
        before = _build()
        raw = two_scene_spec()
        raw["canvas"]["fps"] = 60
        after = VideoSpec.from_dict(raw)

        # every scene's rendering depends on the canvas, so every hash moves
        diff = diff_scene_hashes(scene_hashes(before), scene_hashes(after))
        assert sorted(diff["changed"]) == ["s1", "s2"]

    def test_unknown_scene_raises(self):
        spec = _build()
        with pytest.raises(KeyError):
            scene_sha256(spec, "nope")
