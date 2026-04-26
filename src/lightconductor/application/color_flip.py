"""Pure helper for mirroring per-LED color lists across a topology's
bbox in either the horizontal or vertical axis. Used by the Tag
editor's Flip buttons and by the project-screen Flip shortcuts.

The helper operates on a topology (slave-grid cell indices) and the
parallel ``colors`` list (one RGB triplet per topology cell). It
returns a NEW outer list with mirrored slots; cells whose mirror
target is missing from the topology are left in place. Inner color
triplets are NOT cloned — callers may rely on identity equality on
the inner lists if the outer rebuild is the only mutation.
"""

from __future__ import annotations

from typing import List

from lightconductor.application.topology_bbox import compute_topology_bbox


def _flipped(
    topology: List[int],
    colors: List[List[int]],
    slave_grid_columns: int,
    *,
    axis: str,
) -> List[List[int]]:
    if axis not in ("horizontal", "vertical"):
        raise ValueError(f"axis must be 'horizontal' or 'vertical', got {axis!r}")
    if slave_grid_columns < 1:
        raise ValueError(
            f"slave_grid_columns must be >= 1, got {slave_grid_columns}"
        )
    if len(topology) != len(colors):
        raise ValueError("topology and colors length mismatch")
    if not topology:
        return []

    cols = slave_grid_columns
    min_row, min_col, max_row, max_col = compute_topology_bbox(topology, cols)
    cell_to_idx = {topology[i]: i for i in range(len(topology))}
    new_colors = [c for c in colors]

    for i in range(len(topology)):
        cell = topology[i]
        row = cell // cols
        col = cell % cols
        if axis == "horizontal":
            mirrored_cell = row * cols + (min_col + max_col - col)
        else:
            mirrored_cell = (min_row + max_row - row) * cols + col
        j = cell_to_idx.get(mirrored_cell)
        if j is None:
            continue
        if j <= i:
            continue
        new_colors[i], new_colors[j] = new_colors[j], new_colors[i]
    return new_colors


def flipped_colors_horizontal(
    topology: List[int],
    colors: List[List[int]],
    slave_grid_columns: int,
) -> List[List[int]]:
    """Return a new ``colors`` list mirrored left/right across the
    topology's bbox center column. Cells whose mirror is not in the
    topology are left in place."""
    return _flipped(
        topology, colors, slave_grid_columns, axis="horizontal"
    )


def flipped_colors_vertical(
    topology: List[int],
    colors: List[List[int]],
    slave_grid_columns: int,
) -> List[List[int]]:
    """Return a new ``colors`` list mirrored top/bottom across the
    topology's bbox center row. Cells whose mirror is not in the
    topology are left in place."""
    return _flipped(
        topology, colors, slave_grid_columns, axis="vertical"
    )
