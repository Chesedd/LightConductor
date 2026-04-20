import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.topology_bbox import compute_topology_bbox


class ComputeTopologyBboxTests(unittest.TestCase):
    def test_single_cell_bbox(self):
        self.assertEqual(
            (0, 5, 0, 5),
            compute_topology_bbox([5], 10),
        )

    def test_single_row_bbox(self):
        self.assertEqual(
            (0, 3, 0, 5),
            compute_topology_bbox([3, 5, 4], 10),
        )

    def test_multi_row_bbox(self):
        self.assertEqual(
            (0, 3, 2, 7),
            compute_topology_bbox([3, 15, 27], 10),
        )

    def test_unordered_topology_bbox(self):
        self.assertEqual(
            (0, 3, 2, 7),
            compute_topology_bbox([27, 3, 15], 10),
        )

    def test_empty_topology_raises(self):
        with self.assertRaises(ValueError):
            compute_topology_bbox([], 10)

    def test_zero_grid_columns_raises(self):
        with self.assertRaises(ValueError):
            compute_topology_bbox([0], 0)

    def test_negative_grid_columns_raises(self):
        with self.assertRaises(ValueError):
            compute_topology_bbox([0], -1)

    def test_contiguous_cells_bbox_matches_natural(self):
        bbox = compute_topology_bbox([0, 1, 2, 10, 11, 12], 10)
        self.assertEqual((0, 0, 1, 2), bbox)
        min_row, min_col, max_row, max_col = bbox
        self.assertEqual(2, max_row - min_row + 1)
        self.assertEqual(3, max_col - min_col + 1)


if __name__ == "__main__":
    unittest.main()
