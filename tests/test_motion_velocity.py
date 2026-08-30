"""Gate 12: the pixel-velocity floor must catch sub-1px/frame motion."""

from __future__ import annotations

from colophon.qa.stages.motion_velocity import motion_pixel_velocity
from colophon.spec.schema import VideoSpec

_SPEC = VideoSpec(spec_id="mv-probe", title="motion velocity probe")


def _doc(word_px: int, duration_ms: int = 480, stagger_ms: int = 100) -> str:
    return f"""
    <!doctype html><html><head><style>
    @keyframes word-sweep-in{{from{{transform:translateY({word_px}px)}}to{{transform:none}}}}
    .m-word-sweep .word{{display:inline-block;animation-name:word-sweep-in}}
    @media (prefers-reduced-motion: reduce){{.m-word-sweep .word{{animation:none}}}}
    </style></head><body>
    <div data-composition-id="c1" style="background:#0B0B0D">
      <section id="s1" class="clip" style="background:#0B0B0D">
        <h1 data-motion="word-sweep"><span class="word"
          style="animation-delay:0ms;animation-duration:{duration_ms}ms">Ship</span>
          <span class="word"
          style="animation-delay:{stagger_ms}ms;animation-duration:{duration_ms}ms">it</span></h1>
      </section>
    </div></body></html>
    """


def test_floor_passes_at_16px_per_480ms():
    # 16px / 14.4f @30fps = 1.11px/frame -> clears the floor.
    res = motion_pixel_velocity(_SPEC, document=_doc(16))
    assert res.passed, res.problems
    assert "motion_pixel_velocity" == res.stage_id


def test_floor_fails_at_8px_per_480ms():
    # 8px / 14.4f = 0.56px/frame -> stutters, must be caught.
    res = motion_pixel_velocity(_SPEC, document=_doc(8))
    assert not res.passed
    assert any("word-sweep-in" in p and "px/frame" in p for p in res.problems)


def test_stagger_below_two_frames_fails():
    # 30ms gap @30fps = 0.9f, under the 2-frame minimum.
    res = motion_pixel_velocity(_SPEC, document=_doc(16, stagger_ms=30))
    assert not res.passed
    assert any("stagger" in p for p in res.problems)


def test_no_document_is_advisory():
    res = motion_pixel_velocity(_SPEC, document=None)
    assert res.passed and res.advisory
