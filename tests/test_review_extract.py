"""Luma measurement: the numbers the blank-frame gate decides on.

The scale here is the whole game. Our encodes are yuv420p with
``color_range=tv``, so 8-bit sRGB 0-255 is rescaled to 16-235 before it is
measured. Every downstream threshold is written on that scale, so this file
pins it against real ffmpeg output rather than against a formula.
"""

from __future__ import annotations

import subprocess

import pytest

from colophon.review.extract import LumaStats, luma_stats_at, luminance_at

try:
    # Resolved the way colophon resolves it, so these tests skip exactly when
    # the gate would be unable to measure. `shutil.which` misses ffmpeg on a
    # Homebrew prefix that is not on the test runner's PATH.
    from colophon.runtime import tools

    FFMPEG = str(tools.resolve("ffmpeg").path)
except Exception:  # noqa: BLE001
    FFMPEG = None

needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not resolvable")


# --- the statistic itself -------------------------------------------------


def test_spread_is_the_distance_between_darkest_and_brightest():
    assert LumaStats(18.0, 27.6, 232.0).spread == pytest.approx(214.0)


def test_a_flat_frame_has_zero_spread():
    """A frame showing only its background: every pixel is the same pixel."""
    assert LumaStats(26.0, 26.0, 26.0).spread == pytest.approx(0.0)


def test_spread_is_none_wither_measurement_is_missing():
    """Half a reading is no reading; it must not become a small spread."""
    assert LumaStats(None, 26.0, 26.0).spread is None
    assert LumaStats(26.0, 26.0, None).spread is None
    assert LumaStats(None, None, None).spread is None


def test_luminance_at_still_reports_the_average():
    """Kept for the CLI log; the gate uses the full stats, not this."""
    stats = LumaStats(18.0, 27.6, 232.0)
    assert stats.yavg == pytest.approx(27.6)


# --- the scale, measured against ffmpeg -----------------------------------


@needs_ffmpeg
@pytest.mark.parametrize(
    "colour,expected",
    [
        ("000000", 16.0),   # black  -> the pedestal itself
        ("0B0B12", 26.0),   # our canvas
        ("F5F5F7", 227.0),  # our foreground
        ("FFFFFF", 235.0),  # white  -> the top of the range
    ],
)
def test_solid_colours_land_on_the_16_235_scale(colour, expected):
    """The mapping the whole blank check is calibrated against.

    Verified by encoding a solid colour, not by deriving it. Deriving it is
    how the original 0-255 version shipped and read ~14 units low.
    """
    cmd = [
        FFMPEG, "-v", "info",
        "-f", "lavfi", "-i", f"color=c=0x{colour}:s=320x180:d=1:r=30",
        "-frames:v", "1",
        "-vf", "format=yuv420p,signalstats,metadata=print:file=-",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    measured = {
        name: float(value)
        for name, value in _stats(out)
    }
    assert measured["YAVG"] == pytest.approx(expected, abs=1.0), out[-400:]


@needs_ffmpeg
def test_a_flat_encode_measures_zero_spread_at_any_quality():
    """Compression noise must not look like content.

    If this fails at some crf, BLANK_SPREAD is too low and every flat frame
    at that quality would be reported as drawn.
    """
    for crf in (14, 18, 23, 28):
        subprocess.run(
            [FFMPEG, "-v", "error", "-y", "-f", "lavfi",
             "-i", "color=c=0x0B0B12:s=640x360:d=1:r=30",
             "-frames:v", "1", "-c:v", "libx264", "-crf", str(crf),
             "-pix_fmt", "yuv420p", "flat.mp4"],
            capture_output=True, timeout=120, cwd=_tmpdir(),
        )
        (stats,) = luma_stats_at(f"{_tmpdir()}/flat.mp4", [0.0])
        assert stats.spread == pytest.approx(0.0, abs=1.0), f"crf={crf}: {stats}"


@needs_ffmpeg
def test_luma_stats_at_reads_all_three_statistics():
    subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-f", "lavfi",
         "-i", "color=c=0x0B0B12:s=320x180:d=1:r=30",
         "-frames:v", "1", "-pix_fmt", "yuv420p", "solid.mp4"],
        capture_output=True, timeout=120, cwd=_tmpdir(),
    )
    (stats,) = luma_stats_at(f"{_tmpdir()}/solid.mp4", [0.0])
    assert stats.ymin is not None
    assert stats.yavg is not None
    assert stats.ymax is not None
    assert (luminance_at(f"{_tmpdir()}/solid.mp4", [0.0])[0]) == stats.yavg


# --- scaffolding ----------------------------------------------------------

_TMP = None


def _tmpdir() -> str:
    """A writable directory for scratch encodes (pytest tmp_path is fine)."""
    global _TMP
    if _TMP is None:
        import tempfile

        _TMP = tempfile.mkdtemp(prefix="colophon-luma-")
    return _TMP


def _stats(text: str):
    import re

    return re.findall(r"(Y(?:MIN|LOW|AVG|HIGH|MAX))=([0-9.]+)", text)
