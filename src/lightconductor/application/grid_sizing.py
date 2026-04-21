"""Pure helper for computing a square cell side that fits a grid into
an available area. Used by TopologyDialog, TagPinsDialog, and
LedWireDialog so their cells scale with the dialog's size while
staying square and clickable."""

from __future__ import annotations


def compute_cell_size(
    available_w: int,
    available_h: int,
    rows: int,
    cols: int,
    min_size: int = 6,
) -> int:
    """Return the side length (in pixels) of a square cell that fits a
    rows x cols grid inside an available_w x available_h area.

    The result is ``max(min_size, min(available_w // cols,
    available_h // rows))`` so cells stay square and never shrink
    below ``min_size``. Degenerate inputs (rows or cols <= 0,
    negative available area) collapse to ``min_size``.

    Examples:
        >>> compute_cell_size(100, 100, 10, 10)
        10
        >>> compute_cell_size(200, 100, 10, 10)
        10
        >>> compute_cell_size(40, 40, 10, 10)
        6
        >>> compute_cell_size(0, 0, 0, 0)
        6
    """
    if rows <= 0 or cols <= 0:
        return min_size
    if available_w <= 0 or available_h <= 0:
        return min_size
    return max(min_size, min(available_w // cols, available_h // rows))
