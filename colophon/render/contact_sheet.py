"""Contact-sheet at the VLM-review budget.

R3's contract: a 2576x1456 sheet, never upscale, <=12 frames. The budget is
sized to a vision model's full-detail limit -- larger wastes tokens, smaller
downscales content below what the critic can read.

The sheet is built from extracted PNGs and tiled with ffmpeg. It runs on
every review, no matter how long the video, and the budget is fixed so the
critic never sees a sheet at a different size run to run.

The actual rendered dimensions are within ``max(columns, rows)`` pixels of
the budget on each axis -- integer division in the layout can leave at most
that many pixels short. 2px in 2576 is below the VLM's detail threshold,
and uniform sizing keeps the tile aspect predictable.

The implementation has nothing review-specific about it; this module could
serve any frame-aggregation use case that needs a vision-model-shaped
contact sheet. ``review/extract.py`` is the one current caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..runtime import tools
from ..runtime.tools import run


#: The fixed sheet budget, in pixels. Set so a 92x52 grid of 28px patches
#: exactly fills the sheet; patches below 28px would be unreadable to a
#: vision model at full detail.
SHEET_WIDTH = 2576
SHEET_HEIGHT = 1456

#: Smallest legible tile. Frames are scaled to fit their tile without
#: exceeding it, so anything smaller is letterboxed with the tile background.
#: Going below this would defeat the purpose of the budget.
PATCH_PX = 28

#: Cap on frames per sheet. Beyond ~12 the tiles become postage stamps and
#: the eye reads it as a smear, not a contact sheet. Subsample upstream if
#: you have more.
MAX_FRAMES = 12

TILE_PADDING = 12

#: Gutter/letterbox colour, as bare hex digits with NO "0x" prefix -- the
#: filter strings add it. Interpolating a prefixed value yields
#: ``color=0x0x0B0B0D``, which ffmpeg parses without complaint as RGB
#: (0, 11, 12): the red channel silently drops to zero and the gutter
#: renders with a cyan cast instead of matching the canvas. Verified
#: against ffmpeg 8.x. Matches the canvas the sheet is reviewing.
TILE_BG = "0B0B0D"


class ContactSheetError(RuntimeError):
    """ffmpeg could not build the sheet (separate from layout errors)."""


@dataclass(frozen=True)
class SheetLayout:
    """How the sheet divides into tiles.

    ``tile_w`` and ``tile_h`` are the maximum dimensions a frame may occupy
    in its tile -- frames are scaled down to fit (aspect preserved), then
    letterboxed if they are smaller in one dimension.
    """

    columns: int
    rows: int
    tile_w: int
    tile_h: int

    def __post_init__(self):
        if self.tile_w < PATCH_PX or self.tile_h < PATCH_PX:
            raise ValueError(
                f"tile would be {self.tile_w}x{self.tile_h}; the {PATCH_PX}px "
                f"minimum keeps the sheet readable"
            )


def layout_for(n: int) -> SheetLayout:
    """Pick a grid that fills the sheet at >= PATCH_PX per tile.

    Prefers wider grids (4 cols before 3) because landscape 16:9 frames
    read better in a wider tile. Falls back to fewer columns for fewer
    frames so a 2-frame review still has two big tiles, not one big and
    one postage stamp.
    """
    if n <= 0:
        raise ValueError("at least one frame required")
    if n > MAX_FRAMES:
        raise ValueError(
            f"too many frames ({n}); contract caps at {MAX_FRAMES}. "
            f"Subsample upstream."
        )
    columns = {
        1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 3,
        7: 4, 8: 4, 9: 3, 10: 5, 11: 4, 12: 4,
    }[n]
    rows = (n + columns - 1) // columns
    # ffmpeg's `tile` filter pads between tiles, not at the edges. So a
    # 1-column sheet is exactly SHEET_WIDTH wide; a 2-column sheet is
    # 2*tile_w + 1*padding; etc. We size tile_w to make the rendered sheet
    # match the budget exactly.
    if columns == 1:
        tile_w = SHEET_WIDTH
    else:
        tile_w = (SHEET_WIDTH - TILE_PADDING * (columns - 1)) // columns
    if rows == 1:
        tile_h = SHEET_HEIGHT
    else:
        tile_h = (SHEET_HEIGHT - TILE_PADDING * (rows - 1)) // rows
    return SheetLayout(columns=columns, rows=rows, tile_w=tile_w, tile_h=tile_h)


def build_contact_sheet(
    frame_paths: Sequence[Path],
    out_path: str | Path,
) -> Path:
    """Tile the given frames into a 2576x1456 contact sheet.

    Frames are scaled to fit each tile without upscaling. If a frame is
    smaller than its tile in either dimension, it is centered with a
    letterbox in the tile background. The sheet is written to ``out_path``,
    whose parent directory is created if missing.

    Returns ``out_path``. Raises ``ValueError`` on too few or too many
    frames. Raises ``ContactSheetError`` on ffmpeg failure.
    """
    frames = list(frame_paths)
    if not frames:
        raise ValueError("no frames to tile")
    if len(frames) > MAX_FRAMES:
        raise ValueError(
            f"too many frames ({len(frames)}); cap is {MAX_FRAMES}. "
            f"Subsample upstream -- more frames in a fixed-budget sheet "
            f"means postage-stamp tiles."
        )

    layout = layout_for(len(frames))
    ffmpeg = tools.resolve("ffmpeg")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    inputs: list[str] = []
    for frame in frames:
        inputs += ["-i", str(frame)]

    n = len(frames)
    # ffmpeg 8.x `tile` declares a single input and tiles successive FRAMES
    # of that stream; the multi-input form ("[a][b]tile=2x1") was removed
    # and now fails with "More input link labels specified for filter 'tile'
    # than it has inputs". So concat the stills into one stream, then tile
    # that. Each frame is scaled-down-to-fit with letterbox to keep aspect
    # without upscaling.
    filter_complex = (
        "".join(
            f"[{i}:v]scale={layout.tile_w}:{layout.tile_h}:"
            f"force_original_aspect_ratio=decrease,"
            f"pad={layout.tile_w}:{layout.tile_h}:(ow-iw)/2:(oh-ih)/2:"
            f"color=0x{TILE_BG},setsar=1[s{i}];"
            for i in range(n)
        )
        + "".join(f"[s{i}]" for i in range(n))
        + f"concat=n={n}:v=1:a=0[strip];"
        + f"[strip]tile={layout.columns}x{layout.rows}:"
        f"padding={TILE_PADDING}:color=0x{TILE_BG}[out]"
    )

    code, _, err = run(
        [
            str(ffmpeg.path), "-y", *inputs,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-frames:v", "1",
            "-update", "1",
            str(out_path),
        ],
        timeout=600,
    )
    if code != 0:
        # ffmpeg prints its banner first and the actual reason last, so the
        # head of stderr is always useless. Show the tail, plus the command.
        raise ContactSheetError(
            "contact sheet failed:\n  "
            + (err or "").strip()[-1500:]
            + f"\n  command: {' '.join(str(c) for c in [ffmpeg.path, '-y', *inputs, '-filter_complex', filter_complex])}"
        )
    return out_path