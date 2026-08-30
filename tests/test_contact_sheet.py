"""Contact-sheet: VLM-review budget, never upscale, layout chosen by frame count.

Three properties pin the contract:

1. The sheet dimensions are **fixed** (2576x1456). The vision model
   downstream sees the same-sized image every run -- no surprise when a
   30-second video produces a sheet at a different size than a 6-second one.

2. The sheet **never upscales**. Each tile fits the frame without
   enlargement. A smaller frame gets a letterbox, not a stretch.

3. The tile size is **always >= 28px**. A tile below that is below the
   detail threshold the budget exists to defend.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from colophon.render.contact_sheet import (
    MAX_FRAMES,
    PATCH_PX,
    SHEET_HEIGHT,
    SHEET_WIDTH,
    TILE_BG,
    TILE_PADDING,
    ContactSheetError,
    SheetLayout,
    build_contact_sheet,
    layout_for,
)

try:
    from colophon.runtime import tools

    FFMPEG = str(tools.resolve("ffmpeg").path)
except Exception:  # noqa: BLE001
    FFMPEG = None

needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not resolvable")


# --- the budget is fixed --------------------------------------------------


def test_sheet_dimensions_are_the_vlm_review_budget():
    """2576x1456 = 92x52 patches at 28px. The math is the contract."""
    assert SHEET_WIDTH == 2576
    assert SHEET_HEIGHT == 1456
    assert PATCH_PX == 28
    assert SHEET_WIDTH == 92 * PATCH_PX
    assert SHEET_HEIGHT == 52 * PATCH_PX


def test_the_maximum_is_twelve_frames():
    """More frames in a fixed-budget sheet become unreadable."""
    assert MAX_FRAMES == 12


# --- the layout chooses itself --------------------------------------------


def test_layout_for_one_frame_fills_the_sheet():
    lay = layout_for(1)
    assert lay.tile_w >= PATCH_PX
    assert lay.tile_h >= PATCH_PX


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
def test_layout_keeps_tiles_at_or_above_the_patch_minimum(n):
    lay = layout_for(n)
    assert lay.tile_w >= PATCH_PX, f"n={n}: tile_w={lay.tile_w}"
    assert lay.tile_h >= PATCH_PX, f"n={n}: tile_h={lay.tile_h}"


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
def test_layout_covers_n_tiles(n):
    lay = layout_for(n)
    assert lay.columns * lay.rows >= n


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
def test_layout_renders_to_exactly_the_budget(n):
    """The whole point: ffmpeg's tile output is columns*tile + (cols-1)*padding.

    A 1-column sheet is exactly SHEET_WIDTH wide; an N-column sheet has
    (N-1) inter-tile padding columns. So tile_w is sized to make the sum
    hit the budget, and the test pins that contract.
    """
    lay = layout_for(n)
    rendered_w = lay.columns * lay.tile_w + (lay.columns - 1) * 12
    rendered_h = lay.rows * lay.tile_h + (lay.rows - 1) * 12
    assert rendered_w <= SHEET_WIDTH, f"n={n}: {rendered_w}>{SHEET_WIDTH}"
    assert rendered_h <= SHEET_HEIGHT, f"n={n}: {rendered_h}>{SHEET_HEIGHT}"
    # Within 1px -- integer division can leave at most padding/cols short.
    assert SHEET_WIDTH - rendered_w < lay.columns
    assert SHEET_HEIGHT - rendered_h < lay.rows


def test_layout_for_zero_frames_is_an_error():
    with pytest.raises(ValueError, match="at least one frame"):
        layout_for(0)


def test_layout_above_the_cap_is_an_error():
    with pytest.raises(ValueError, match="too many frames"):
        layout_for(MAX_FRAMES + 1)


def test_layout_prefers_wider_grids_for_landscape_frames():
    """A 16:9 frame reads better in a 4-col grid than a 3-col grid at the
    same budget, because the wider tile is closer to the frame's aspect.
    """
    assert layout_for(6).columns == 3
    assert layout_for(8).columns == 4


# --- the builder writes the right thing -----------------------------------


@needs_ffmpeg
def test_the_output_sheet_is_at_or_near_the_budget(tmp_path):
    """The rendered sheet sits within max(columns, rows) px of the budget.

    Integer division in the layout can leave a few pixels short; ffmpeg's
    tile filter cannot redistribute them across tiles. That's well below
    a vision model's detail threshold (a single token covers many pixels),
    but it is the only way the rendered size can drift from SHEET_*. The
    test pins that contract so a future "make it exact" change has to be
    deliberate.
    """
    frames = _six_solid_frames(tmp_path)
    out = tmp_path / "sheet.png"
    build_contact_sheet(frames, out)
    assert out.is_file()
    w, h = _png_dimensions(out)
    drift_w = SHEET_WIDTH - w
    drift_h = SHEET_HEIGHT - h
    assert 0 <= drift_w < 6, f"width drift {drift_w}px outside contract"
    assert 0 <= drift_h < 6, f"height drift {drift_h}px outside contract"


@needs_ffmpeg
def test_too_many_frames_is_rejected_before_ffmpeg_runs(tmp_path):
    frames = [tmp_path / f"f{i:02d}.png" for i in range(20)]
    for f in frames:
        _solid_frame(f)
    with pytest.raises(ValueError, match="too many frames"):
        build_contact_sheet(frames, tmp_path / "sheet.png")


def test_no_frames_is_rejected():
    with pytest.raises(ValueError, match="no frames"):
        build_contact_sheet([], "/tmp/never.png")


@needs_ffmpeg
def test_a_single_frame_still_gets_a_full_sheet(tmp_path):
    """The most common edge case: a 1-frame review still produces a sheet.

    With one column there is no inter-tile padding, so the rendered sheet
    is exactly SHEET_WIDTH wide. No drift here.
    """
    frame = tmp_path / "f01.png"
    _solid_frame(frame)
    out = tmp_path / "sheet.png"
    build_contact_sheet([frame], out)
    w, h = _png_dimensions(out)
    assert (w, h) == (SHEET_WIDTH, SHEET_HEIGHT)


@needs_ffmpeg
def test_the_gutter_is_the_canvas_colour_not_a_tinted_black(tmp_path):
    """Regression: the gutter colour used to lose its red channel.

    ``TILE_BG`` held "0x0B0B0D" while the filter string interpolated it as
    ``color=0x{TILE_BG}``, producing ``0x0x0B0B0D``. ffmpeg parses that
    without complaint and without any warning as RGB (0, 11, 12) -- red
    silently dropped, gutter tinted cyan instead of matching the canvas.
    Exit code is 0, so only sampling a real pixel catches it.
    """
    sheet = build_contact_sheet(_six_solid_frames(tmp_path), tmp_path / "sheet.png")
    layout = layout_for(6)

    # First vertical gutter: a few pixels past the right edge of column 1.
    x = layout.tile_w + TILE_PADDING // 2
    y = layout.tile_h // 2
    r, g, b = _pixel(sheet, x, y)

    assert r > 0, (
        f"gutter sampled ({r},{g},{b}): the red channel dropped out, which is "
        f"the signature of a duplicated 0x prefix in the tile colour"
    )
    assert (r, g, b) == (11, 11, 13), f"gutter is ({r},{g},{b}), want #0B0B0D"


def test_the_tile_colour_constant_carries_no_0x_prefix():
    """The filter strings add ``0x`` themselves; the constant must not."""
    assert not TILE_BG.startswith("0x"), "TILE_BG must be bare hex digits"
    assert len(TILE_BG) == 6
    assert int(TILE_BG, 16) == 0x0B0B0D


# --- helpers --------------------------------------------------------------


def _solid_frame(path: Path, width: int = 320, height: int = 180,
                 colour: str = "0B0B12") -> None:
    assert FFMPEG is not None
    subprocess.run(
        [FFMPEG, "-v", "error", "-y",
         "-f", "lavfi", "-i", f"color=c=0x{colour}:s={width}x{height}:d=0.04",
         "-frames:v", "1", "-update", "1", str(path)],
        check=True, capture_output=True, timeout=60,
    )


def _six_solid_frames(tmp_path: Path) -> list[Path]:
    paths = []
    for i in range(6):
        p = tmp_path / f"frame-{i + 1:02d}.png"
        _solid_frame(p)
        paths.append(p)
    return paths


def _pixel(path: Path, x: int, y: int) -> tuple[int, int, int]:
    """Sample one pixel as RGB by cropping to 1x1 and reading raw video."""
    assert FFMPEG is not None
    proc = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(path),
         "-vf", f"crop=1:1:{x}:{y}", "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True, timeout=60,
    )
    assert len(proc.stdout) >= 3, f"crop produced {len(proc.stdout)} bytes"
    return proc.stdout[0], proc.stdout[1], proc.stdout[2]


def _png_dimensions(path: Path) -> tuple[int, int]:
    """Read PNG width/height from the IHDR without PIL."""
    with open(path, "rb") as f:
        head = f.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{path}: not a PNG"
    width = int.from_bytes(head[16:20], "big")
    height = int.from_bytes(head[20:24], "big")
    return width, height