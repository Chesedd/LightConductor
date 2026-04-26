"""Tests for ``lightconductor.application.color_flip``.

The helper is pure-Python with a single dependency on
``compute_topology_bbox``. Tests exercise horizontal/vertical mirror
across a variety of bbox shapes, including L-shaped topologies whose
"orphan" cells (mirror target absent from topology) must remain in
place.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.color_flip import (
    flipped_colors_horizontal,
    flipped_colors_vertical,
)

# ---------------------------------------------------------------------------
# Horizontal — basic shapes
# ---------------------------------------------------------------------------


def test_horizontal_flip_3x1_strip_swaps_endpoints():
    topology = [0, 1, 2]
    colors = [[255, 0, 0], [0, 255, 0], [0, 0, 255]]
    out = flipped_colors_horizontal(topology, colors, slave_grid_columns=3)
    assert out == [[0, 0, 255], [0, 255, 0], [255, 0, 0]]


def test_horizontal_flip_2x2_block_swaps_columns():
    topology = [0, 1, 3, 4]
    colors = [[1, 1, 1], [2, 2, 2], [3, 3, 3], [4, 4, 4]]
    out = flipped_colors_horizontal(topology, colors, slave_grid_columns=3)
    assert out == [[2, 2, 2], [1, 1, 1], [4, 4, 4], [3, 3, 3]]


# ---------------------------------------------------------------------------
# Vertical — basic shapes
# ---------------------------------------------------------------------------


def test_vertical_flip_2x2_block_swaps_rows():
    topology = [0, 1, 3, 4]
    colors = [[1, 1, 1], [2, 2, 2], [3, 3, 3], [4, 4, 4]]
    out = flipped_colors_vertical(topology, colors, slave_grid_columns=3)
    assert out == [[3, 3, 3], [4, 4, 4], [1, 1, 1], [2, 2, 2]]


# ---------------------------------------------------------------------------
# Asymmetric / L-shape — orphan cells stay
# ---------------------------------------------------------------------------


def test_horizontal_flip_asymmetric_l_shape_keeps_orphans():
    """L-shape: column 0 (rows 0,1,2) plus row 2 (cols 1,2). The bbox
    is rows 0..2, cols 0..2. Cells 0 (r0c0) and 3 (r1c0) mirror to
    cells 2 and 5 respectively, neither of which are in the topology
    — so those entries stay put. Cell 6 (r2c0) mirrors to cell 8
    (r2c2), which IS in the topology → swap. Cell 7 (r2c1) is the
    middle column on row 2 → self-mirror, no swap."""
    topology = [0, 3, 6, 7, 8]
    A, B, C, D, E = [1, 1, 1], [2, 2, 2], [3, 3, 3], [4, 4, 4], [5, 5, 5]
    colors = [A, B, C, D, E]
    out = flipped_colors_horizontal(topology, colors, slave_grid_columns=3)
    assert out == [A, B, E, D, C]


def test_vertical_flip_l_shape_swaps_correctly():
    """Same L-shape under vertical flip. bbox rows 0..2.
    Cell 0 (r0) mirrors r2, col 0 → cell 6 (in topology) → swap A↔C.
    Cell 3 (r1c0) mirrors r1c0 — itself (middle row) → no swap.
    Cell 6 already paired above (j<=i continue).
    Cell 7 (r2c1) mirrors r0c1 = cell 1 → NOT in topology → stay D.
    Cell 8 (r2c2) mirrors r0c2 = cell 2 → NOT in topology → stay E.
    Expected: [C, B, A, D, E]."""
    topology = [0, 3, 6, 7, 8]
    A, B, C, D, E = [1, 1, 1], [2, 2, 2], [3, 3, 3], [4, 4, 4], [5, 5, 5]
    colors = [A, B, C, D, E]
    out = flipped_colors_vertical(topology, colors, slave_grid_columns=3)
    assert out == [C, B, A, D, E]


# ---------------------------------------------------------------------------
# Involutions — flipping twice returns to original
# ---------------------------------------------------------------------------


def test_double_horizontal_flip_is_identity():
    topology = [0, 1, 2, 5, 8]
    colors = [[10, 0, 0], [20, 0, 0], [30, 0, 0], [40, 0, 0], [50, 0, 0]]
    once = flipped_colors_horizontal(topology, colors, slave_grid_columns=3)
    twice = flipped_colors_horizontal(topology, once, slave_grid_columns=3)
    assert twice == colors


def test_double_vertical_flip_is_identity():
    topology = [0, 3, 6, 7, 8]
    colors = [[10, 0, 0], [20, 0, 0], [30, 0, 0], [40, 0, 0], [50, 0, 0]]
    once = flipped_colors_vertical(topology, colors, slave_grid_columns=3)
    twice = flipped_colors_vertical(topology, once, slave_grid_columns=3)
    assert twice == colors


# ---------------------------------------------------------------------------
# Immutability of input
# ---------------------------------------------------------------------------


def test_flip_does_not_mutate_input():
    topology = [0, 1, 2]
    inner_a = [255, 0, 0]
    inner_b = [0, 255, 0]
    inner_c = [0, 0, 255]
    colors = [inner_a, inner_b, inner_c]
    snapshot = [list(c) for c in colors]
    out = flipped_colors_horizontal(topology, colors, slave_grid_columns=3)
    # Outer list untouched.
    assert colors == snapshot
    assert colors[0] is inner_a and colors[1] is inner_b and colors[2] is inner_c
    # And the result is a NEW outer list.
    assert out is not colors


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_flip_empty_topology_returns_empty():
    assert flipped_colors_horizontal([], [], slave_grid_columns=3) == []
    assert flipped_colors_vertical([], [], slave_grid_columns=3) == []


def test_length_mismatch_raises_value_error():
    with pytest.raises(ValueError, match="length mismatch"):
        flipped_colors_horizontal([0, 1, 2], [[0, 0, 0]], slave_grid_columns=3)
    with pytest.raises(ValueError, match="length mismatch"):
        flipped_colors_vertical([0, 1, 2], [[0, 0, 0]], slave_grid_columns=3)


def test_invalid_grid_columns_raises_value_error():
    with pytest.raises(ValueError):
        flipped_colors_horizontal([0], [[0, 0, 0]], slave_grid_columns=0)
    with pytest.raises(ValueError):
        flipped_colors_horizontal([0], [[0, 0, 0]], slave_grid_columns=-1)
    with pytest.raises(ValueError):
        flipped_colors_vertical([0], [[0, 0, 0]], slave_grid_columns=0)
    with pytest.raises(ValueError):
        flipped_colors_vertical([0], [[0, 0, 0]], slave_grid_columns=-1)


def test_single_cell_topology_returns_unchanged_copy():
    topology = [4]
    colors = [[7, 7, 7]]
    h = flipped_colors_horizontal(topology, colors, slave_grid_columns=3)
    v = flipped_colors_vertical(topology, colors, slave_grid_columns=3)
    assert h == colors
    assert v == colors
    assert h is not colors
    assert v is not colors


def test_horizontal_flip_with_self_mirror_central_column():
    """Odd-width 5-cell strip. Cell 2 is the bbox center column;
    it mirrors to itself → must stay put. Pairs (0,4) and (1,3)
    swap."""
    topology = [0, 1, 2, 3, 4]
    A, B, C, D, E = [1, 0, 0], [2, 0, 0], [3, 0, 0], [4, 0, 0], [5, 0, 0]
    colors = [A, B, C, D, E]
    out = flipped_colors_horizontal(topology, colors, slave_grid_columns=5)
    assert out == [E, D, C, B, A]
