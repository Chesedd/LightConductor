import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.patterns import (
    apply_fill_range,
    build_timed_pattern_tags,
    floating_gradient_frames,
    moving_window_frames,
    sequential_fill_frames,
    solid_fill,
)


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

    def test_sequential_fill_frames(self):
        frames = sequential_fill_frames(3, [5, 6, 7])
        self.assertEqual(
            [
                [[5, 6, 7], [0, 0, 0], [0, 0, 0]],
                [[5, 6, 7], [5, 6, 7], [0, 0, 0]],
                [[5, 6, 7], [5, 6, 7], [5, 6, 7]],
            ],
            frames,
        )

    def test_moving_window_frames(self):
        frames = moving_window_frames(4, 2, [1, 2, 3])
        self.assertEqual(3, len(frames))
        self.assertEqual([[1, 2, 3], [1, 2, 3], [0, 0, 0], [0, 0, 0]], frames[0])
        self.assertEqual([[0, 0, 0], [0, 0, 0], [1, 2, 3], [1, 2, 3]], frames[-1])

    def test_floating_gradient_frames(self):
        frames = floating_gradient_frames(3, [100, 0, 0], width=2)
        self.assertEqual(3, len(frames))
        self.assertEqual([100, 0, 0], frames[1][1])
        self.assertEqual([50, 0, 0], frames[1][0])

    def test_build_timed_pattern_tags(self):
        tags = build_timed_pattern_tags(
            frames=[[[1, 1, 1]], [[2, 2, 2]]],
            start_time=0.0,
            end_time=0.5,
            step=0.25,
        )
        self.assertEqual([0.0, 0.25, 0.5], [tag["time"] for tag in tags])
        self.assertEqual([[1, 1, 1]], tags[0]["colors"])
        self.assertEqual([[2, 2, 2]], tags[1]["colors"])


if __name__ == "__main__":
    unittest.main()
