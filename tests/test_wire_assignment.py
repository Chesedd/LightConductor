import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.wire_assignment import (
    add_to_wire,
    build_linear_wire,
    remove_from_wire,
    validate_wire_assignment,
)


class ValidateWireAssignmentTests(unittest.TestCase):
    def test_valid_linear_assignment_returns_no_errors(self):
        self.assertEqual(
            validate_wire_assignment([0, 1, 2], 4, 3),
            [],
        )

    def test_valid_custom_order_no_errors(self):
        self.assertEqual(
            validate_wire_assignment([3, 0, 2, 1], 4, 4),
            [],
        )

    def test_length_mismatch_reports_error(self):
        errors = validate_wire_assignment([0, 1], 4, 3)
        self.assertEqual(len(errors), 1)
        self.assertIn("length 2", errors[0])
        self.assertIn("led_count 3", errors[0])

    def test_duplicate_cell_reports_error(self):
        errors = validate_wire_assignment([0, 1, 1], 4, 3)
        dup_errors = [e for e in errors if "duplicate" in e]
        self.assertEqual(len(dup_errors), 1)
        self.assertIn("1", dup_errors[0])

    def test_out_of_range_cell_reports_error(self):
        errors = validate_wire_assignment([0, 5], 4, 2)
        range_errors = [e for e in errors if "out of canvas" in e]
        self.assertEqual(len(range_errors), 1)
        self.assertIn("5", range_errors[0])

    def test_canvas_size_zero_short_circuits(self):
        errors = validate_wire_assignment([0, 1], 0, 2)
        self.assertEqual(len(errors), 1)
        self.assertIn("canvas_size", errors[0])

    def test_negative_led_count_reports_error(self):
        errors = validate_wire_assignment([], 10, -1)
        led_errors = [e for e in errors if "led_count" in e]
        self.assertTrue(len(led_errors) >= 1)


class BuildLinearWireTests(unittest.TestCase):
    def test_build_linear_wire_zero_returns_empty(self):
        self.assertEqual(build_linear_wire(0), [])

    def test_build_linear_wire_ten_returns_range(self):
        self.assertEqual(
            build_linear_wire(10),
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        )


class AddRemoveWireTests(unittest.TestCase):
    def test_add_and_remove_roundtrip(self):
        self.assertEqual(add_to_wire([0, 2], 1), [0, 2, 1])
        self.assertEqual(remove_from_wire([0, 2, 1], 2), [0, 1])


if __name__ == "__main__":
    unittest.main()
