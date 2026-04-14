import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.patterns import apply_fill_range, solid_fill


class PatternsTests(unittest.TestCase):
    def test_solid_fill(self):
        self.assertEqual([[1, 2, 3], [1, 2, 3], [1, 2, 3]], solid_fill(3, [1, 2, 3]))

    def test_solid_fill_zero(self):
        self.assertEqual([], solid_fill(0, [1, 2, 3]))

    def test_apply_fill_range(self):
        colors = [[0, 0, 0] for _ in range(5)]
        filled = apply_fill_range(colors, 1, 3, [9, 8, 7])
        self.assertEqual(
            [[0, 0, 0], [9, 8, 7], [9, 8, 7], [9, 8, 7], [0, 0, 0]],
            filled,
        )

    def test_apply_fill_range_reversed_and_clamped(self):
        colors = [[0, 0, 0] for _ in range(3)]
        filled = apply_fill_range(colors, 10, -2, [1, 1, 1])
        self.assertEqual([[1, 1, 1], [1, 1, 1], [1, 1, 1]], filled)


if __name__ == "__main__":
    unittest.main()
