import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.range_allocator import available_starts


class RangeAllocatorTests(unittest.TestCase):
    def test_returns_available_starts_without_overlap(self):
        starts = available_starts(led_count=10, occupied_ranges=[(2, 3), (7, 2)], length=2)
        self.assertEqual([0, 5], starts)

    def test_empty_on_invalid_length(self):
        self.assertEqual([], available_starts(10, [(2, 3)], 0))
        self.assertEqual([], available_starts(10, [(2, 3)], 11))


if __name__ == "__main__":
    unittest.main()
