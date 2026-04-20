"""Pure helper for computing the bounding box of a topology within a
slave's grid. Used by TagPinsDialog to lay out a compact per-LED
color editor showing only the bbox around active cells instead of
the full slave grid."""

from __future__ import annotations

from typing import List, Tuple


def compute_topology_bbox(
    topology: List[int],
    slave_grid_columns: int,
) -> Tuple[int, int, int, int]:
    """Return (min_row, min_col, max_row, max_col) inclusive for
    cells in topology.

    Raises ValueError if topology is empty or slave_grid_columns < 1."""
    if slave_grid_columns < 1:
        raise ValueError(f"slave_grid_columns must be >= 1, got {slave_grid_columns}")
    if not topology:
        raise ValueError("topology must not be empty")
    rows = [c // slave_grid_columns for c in topology]
    cols = [c % slave_grid_columns for c in topology]
    return (min(rows), min(cols), max(rows), max(cols))
