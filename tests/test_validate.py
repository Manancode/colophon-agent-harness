"""Structural validation, and the rule that unknown keys are never dropped.

``reject_unknown_keys`` exists because an earlier normaliser rebuilt scenes
from a fixed key set and silently discarded the rest — which is how
``treatment`` vanished when it was first added. The symptom surfaced later as
"six scenes all rendered with the default layout". These tests are the
regression guard for that entire class of bug.
"""

from __future__ import annotations

import pytest

from colophon.spec.schema import SpecError, VideoSpec
from colophon.spec.validate import assert_valid, reject_unknown_keys, validate

from .conftest import scene, spec_dict


class TestNeverSilentlyDrop:
    def test_unknown_top_level_key_raises(self):
        raw = spec_dict()
        raw["playback_speed"] = 1.25
        with pytest.raises(SpecError, match="playback_speed"):
            reject_unknown_keys(raw)

    def test_unknown_scene_key_raises(self):
        raw = spec_dict()
        raw["scenes"][0]["zoomInTo"] = True
        with pytest.raises(SpecError, match=r"scenes\[0\]"):
            reject_unknown_keys(raw)

    def test_unknown_canvas_key_raises(self):
        raw = spec_dict()
        raw["canvas"]["pixelRatio"] = 2
        with pytest.raises(SpecError, match="canvas"):
            reject_unknown_keys(raw)

    def test_unknown_claim_key_raises(self):
        raw = spec_dict()
        raw["claims"][0]["confidence"] = 0.9
        with pytest.raises(SpecError, match=r"claims\[0\]"):
            reject_unknown_keys(raw)

    def test_the_error_names_every_offending_key(self):
        raw = spec_dict()
        raw["alpha"] = 1
        raw["beta"] = 2
        with pytest.raises(SpecError) as excinfo:
            reject_unknown_keys(raw)
        message = str(excinfo.value)
        assert "alpha" in message and "beta" in message

    def test_known_keys_pass(self):
        reject_unknown_keys(spec_dict())


class TestValidate:
    def test_a_minimal_spec_is_clean(self):
        assert validate(VideoSpec.from_dict(spec_dict())) == []

    def test_assert_valid_raises_with_every_problem_listed(self):
        raw = spec_dict(canvas={"width": 0, "height": -5, "fps": 31, "background": "#000"})
        raw["brand"]["tokens"] = {}
        with pytest.raises(SpecError) as excinfo:
            assert_valid(VideoSpec.from_dict(raw))
        message = str(excinfo.value)
        assert "fps" in message
        assert "'bg'" in message

    def test_unsupported_fps_is_reported(self):
        raw = spec_dict(canvas={"width": 1920, "height": 1080, "fps": 23, "background": "#000"})
        assert any("fps" in p for p in validate(VideoSpec.from_dict(raw)))

    def test_remote_assets_are_rejected(self):
        raw = spec_dict(
            assets=[{"asset_id": "a1", "kind": "image", "path": "https://cdn.example.com/x.png"}]
        )
        problems = validate(VideoSpec.from_dict(raw))
        assert any("remote assets are not permitted" in p for p in problems)

    def test_a_claim_nothing_references_is_reported(self):
        raw = spec_dict()
        raw["claims"].append({"claim_id": "orphan", "text": "Nobody binds me", "kind": "narration"})
        problems = validate(VideoSpec.from_dict(raw))
        assert any("orphan" in p for p in problems)

    def test_title_claim_must_be_of_kind_title(self):
        raw = spec_dict()
        raw["scenes"][0]["title_claim_id"] = "n1"
        raw["scenes"][0]["narration_claim_id"] = None
        problems = validate(VideoSpec.from_dict(raw))
        assert any("expected 'title'" in p for p in problems)

    def test_unknown_role_is_reported(self):
        raw = spec_dict(scenes=[scene("s1", role="vibes")])
        problems = validate(VideoSpec.from_dict(raw))
        assert any("role 'vibes'" in p for p in problems)

    def test_non_positive_duration_is_reported(self):
        raw = spec_dict(scenes=[scene("s1", duration_s=0)])
        problems = validate(VideoSpec.from_dict(raw))
        assert any("duration_s must be > 0" in p for p in problems)


class TestTimelineValidation:
    def test_match_cut_without_overlap_is_rejected(self):
        raw = spec_dict(
            timeline={"policy": "adjacent", "overlap_s": 0.0, "transition": "match_cut", "transition_ms": 400}
        )
        problems = validate(VideoSpec.from_dict(raw))
        assert any("match_cut" in p for p in problems)

    def test_match_cut_with_overlap_is_accepted(self):
        raw = spec_dict(
            timeline={"policy": "adjacent", "overlap_s": 0.25, "transition": "match_cut", "transition_ms": 400}
        )
        assert not [p for p in validate(VideoSpec.from_dict(raw)) if "match_cut" in p]

    def test_explicit_policy_is_rejected_in_v0(self):
        raw = spec_dict(
            timeline={"policy": "explicit", "overlap_s": 0.0, "transition": "cut", "transition_ms": 0}
        )
        problems = validate(VideoSpec.from_dict(raw))
        assert any("not supported in V0" in p for p in problems)

    def test_negative_overlap_is_rejected(self):
        raw = spec_dict(
            timeline={"policy": "adjacent", "overlap_s": -1.0, "transition": "cut", "transition_ms": 0}
        )
        problems = validate(VideoSpec.from_dict(raw))
        assert any("overlap_s must be >= 0" in p for p in problems)
