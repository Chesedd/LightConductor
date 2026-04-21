import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.grid_sizing import compute_cell_size


class ComputeCellSizeTests(unittest.TestCase):
    def test_square_area_equal_rows_cols(self):
        self.assertEqual(10, compute_cell_size(100, 100, 10, 10))

    def test_wide_aspect_is_height_constrained(self):
        # 400 wide / 10 cols = 40 per col; 100 tall / 10 rows = 10 per row.
        # min wins -> 10.
        self.assertEqual(10, compute_cell_size(400, 100, 10, 10))

    def test_tall_aspect_is_width_constrained(self):
        # 100 wide / 10 cols = 10 per col; 400 tall / 10 rows = 40 per row.
        # min wins -> 10.
        self.assertEqual(10, compute_cell_size(100, 400, 10, 10))

    def test_too_small_clamps_to_min(self):
        # 20x20 area, 10x10 grid => 2 per cell, below default 6 floor.
        self.assertEqual(6, compute_cell_size(20, 20, 10, 10))

    def test_zero_rows_returns_min(self):
        self.assertEqual(6, compute_cell_size(100, 100, 0, 10))

    def test_zero_cols_returns_min(self):
        self.assertEqual(6, compute_cell_size(100, 100, 10, 0))

    def test_negative_area_returns_min(self):
        self.assertEqual(6, compute_cell_size(-50, 100, 10, 10))
        self.assertEqual(6, compute_cell_size(100, -50, 10, 10))

    def test_large_canvas_in_medium_viewport(self):
        # 50x50 grid in 800x600 area: 800//50=16, 600//50=12 -> 12.
        size = compute_cell_size(800, 600, 50, 50)
        self.assertEqual(12, size)
        self.assertGreaterEqual(size, 6)

    def test_custom_min_size_honored(self):
        # 20x20 area, 10x10 grid => 2 per cell, custom floor 4.
        self.assertEqual(4, compute_cell_size(20, 20, 10, 10, min_size=4))

    def test_grows_unbounded_with_window(self):
        self.assertEqual(80, compute_cell_size(800, 800, 10, 10))


if __name__ == "__main__":
    unittest.main()
