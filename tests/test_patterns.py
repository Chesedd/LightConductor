import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.patterns import solid_fill


class PatternsTests(unittest.TestCase):
    def test_solid_fill(self):
        self.assertEqual([[1, 2, 3], [1, 2, 3], [1, 2, 3]], solid_fill(3, [1, 2, 3]))

    def test_solid_fill_zero(self):
        self.assertEqual([], solid_fill(0, [1, 2, 3]))


if __name__ == "__main__":
    unittest.main()
