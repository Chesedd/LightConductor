import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.grid_zoom import (
    DEFAULT_MAX_CELL,
    DEFAULT_MIN_CELL,
    DEFAULT_STEP,
    apply_wheel_zoom,
)


class ApplyWheelZoomTests(unittest.TestCase):
    def test_zoom_in_multiplies_by_step(self) -> None:
        # 16 * 1.15 = 18.4 -> 18
        self.assertEqual(18, apply_wheel_zoom(16, 120))

    def test_zoom_out_divides_by_step(self) -> None:
        # 16 / 1.15 = 13.913... -> 13
        self.assertEqual(13, apply_wheel_zoom(16, -120))

    def test_zero_delta_leaves_size_unchanged(self) -> None:
        self.assertEqual(16, apply_wheel_zoom(16, 0))

    def test_zoom_in_at_max_is_clamped(self) -> None:
        self.assertEqual(DEFAULT_MAX_CELL, apply_wheel_zoom(DEFAULT_MAX_CELL, 120))

    def test_zoom_out_at_min_is_clamped(self) -> None:
        self.assertEqual(DEFAULT_MIN_CELL, apply_wheel_zoom(DEFAULT_MIN_CELL, -120))

    def test_zoom_in_near_max_clamps_to_max(self) -> None:
        # 60 * 1.15 = 69 -> clamp to 64, not 69.
        self.assertEqual(DEFAULT_MAX_CELL, apply_wheel_zoom(60, 120))

    def test_zoom_out_near_min_clamps_to_min(self) -> None:
        # 7 / 1.15 = 6.08... -> 6 (not something below 6).
        self.assertEqual(DEFAULT_MIN_CELL, apply_wheel_zoom(7, -120))

    def test_repeated_zoom_in_monotonically_approaches_max(self) -> None:
        size = 16
        seen = [size]
        for _ in range(40):
            new = apply_wheel_zoom(size, 120)
            self.assertGreaterEqual(new, size)
            size = new
            seen.append(size)
        self.assertEqual(DEFAULT_MAX_CELL, size)
        # Each step is strictly increasing until it plateaus at max.
        plateau_index = seen.index(DEFAULT_MAX_CELL)
        for i in range(plateau_index):
            self.assertLess(seen[i], seen[i + 1])

    def test_zoom_in_from_min_makes_progress(self) -> None:
        # Without the ±1 guard, int(6 * 1.15) == 6 would get stuck.
        self.assertEqual(7, apply_wheel_zoom(DEFAULT_MIN_CELL, 120))

    def test_custom_step_and_bounds_respected(self) -> None:
        # With step=2.0 and bounds [1, 100], 10 -> 20 -> 40 -> 80 -> 100.
        size = 10
        size = apply_wheel_zoom(size, 1, min_size=1, max_size=100, step=2.0)
        self.assertEqual(20, size)
        size = apply_wheel_zoom(size, 1, min_size=1, max_size=100, step=2.0)
        self.assertEqual(40, size)
        size = apply_wheel_zoom(size, 1, min_size=1, max_size=100, step=2.0)
        self.assertEqual(80, size)
        size = apply_wheel_zoom(size, 1, min_size=1, max_size=100, step=2.0)
        self.assertEqual(100, size)

    def test_default_constants_match_signature_defaults(self) -> None:
        self.assertEqual(6, DEFAULT_MIN_CELL)
        self.assertEqual(64, DEFAULT_MAX_CELL)
        self.assertAlmostEqual(1.15, DEFAULT_STEP)


if __name__ == "__main__":
    unittest.main()
