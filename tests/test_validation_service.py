import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.validation_service import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    ValidationIssue,
    ValidationService,
)
from lightconductor.domain.models import Master, Slave, TagType


def _tag_type(name, pin, topology=None, rows=1, columns=1):
    return TagType(
        name=name,
        pin=str(pin),
        rows=rows,
        columns=columns,
        color=[255, 255, 255],
        topology=list(topology) if topology is not None else [],
        tags=[],
    )


def _slave(
    slave_id="s1",
    name="Slave",
    pin="0",
    led_count=0,
    tag_types=None,
    grid_rows=None,
    grid_columns=None,
    led_cells=None,
):
    if grid_rows is None and grid_columns is None:
        grid_rows = 1
        grid_columns = max(1, led_count)
    elif grid_rows is None:
        grid_rows = 1
    elif grid_columns is None:
        grid_columns = max(1, led_count)
    if led_cells is None:
        led_cells = list(range(led_count))
    return Slave(
        id=slave_id,
        name=name,
        pin=str(pin),
        led_count=led_count,
        grid_rows=grid_rows,
        grid_columns=grid_columns,
        led_cells=list(led_cells),
        tag_types=dict(tag_types or {}),
    )


def _master(master_id="m1", name="Master", ip="192.168.0.1", slaves=None):
    return Master(
        id=master_id,
        name=name,
        ip=ip,
        slaves=dict(slaves or {}),
    )


class ValidationServiceHappyPathTests(unittest.TestCase):
    def setUp(self):
        self.service = ValidationService()

    def test_no_issues_for_empty_masters(self):
        self.assertEqual([], self.service.validate({}))

    def test_no_issues_for_valid_single_master(self):
        tt = _tag_type("front", "0", topology=[0, 1, 2, 3, 4])
        slave = _slave(pin="0", led_count=5, tag_types={"front": tt})
        master = _master(ip="10.0.0.1", slaves={"s1": slave})
        self.assertEqual([], self.service.validate({"m1": master}))

    def test_no_issues_for_valid_multi_slave_multi_tag_type(self):
        t_a = _tag_type("a", "0", topology=[0, 1, 2])
        t_b = _tag_type("b", "3", topology=[0, 1])
        s1 = _slave("s1", pin="1", led_count=5, tag_types={"a": t_a, "b": t_b})
        t_c = _tag_type("c", "0", topology=[0, 1, 2, 3])
        s2 = _slave("s2", pin="2", led_count=4, tag_types={"c": t_c})
        master = _master(ip="192.168.0.10", slaves={"s1": s1, "s2": s2})
        self.assertEqual([], self.service.validate({"m1": master}))


class ValidationServiceOverlapAndBoundsTests(unittest.TestCase):
    def setUp(self):
        self.service = ValidationService()

    def test_detects_segment_overlap_in_slave(self):
        t1 = _tag_type("a", "0", topology=[0, 1, 2, 3])
        t2 = _tag_type("b", "3", topology=[0, 1, 2])
        slave = _slave(pin="0", led_count=10, tag_types={"a": t1, "b": t2})
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        overlaps = [i for i in issues if i.category == "overlap"]
        self.assertEqual(1, len(overlaps))
        self.assertEqual(SEVERITY_ERROR, overlaps[0].severity)
        self.assertEqual("masters.m1.slaves.s1", overlaps[0].path)

    def test_detects_segment_out_of_bounds(self):
        tt = _tag_type("a", "8", topology=[0, 1, 2, 3])
        slave = _slave(pin="0", led_count=10, tag_types={"a": tt})
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        oob = [i for i in issues if i.category == "out_of_bounds"]
        self.assertEqual(1, len(oob))
        self.assertEqual(SEVERITY_ERROR, oob[0].severity)
        self.assertEqual(
            "masters.m1.slaves.s1.tag_types.a",
            oob[0].path,
        )

    def test_no_out_of_bounds_when_canvas_is_zero(self):
        tt = _tag_type("a", "100", topology=[0, 1, 2, 3])
        slave = _slave(
            pin="0",
            led_count=0,
            grid_rows=0,
            grid_columns=0,
            led_cells=[],
            tag_types={"a": tt},
        )
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        self.assertFalse(any(i.category == "out_of_bounds" for i in issues))


class ValidationServiceDuplicateSegmentStartTests(unittest.TestCase):
    def setUp(self):
        self.service = ValidationService()

    def test_detects_duplicate_segment_starts(self):
        t1 = _tag_type("a", "5", topology=[0, 1])
        t2 = _tag_type("b", "5", topology=[0, 1, 2])
        slave = _slave(pin="0", led_count=20, tag_types={"a": t1, "b": t2})
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        dups = [i for i in issues if i.category == "duplicate_segment_start"]
        self.assertEqual(1, len(dups))
        self.assertEqual(SEVERITY_ERROR, dups[0].severity)
        overlaps = [i for i in issues if i.category == "overlap"]
        self.assertEqual(0, len(overlaps))


class ValidationServiceDuplicateSlavePinTests(unittest.TestCase):
    def setUp(self):
        self.service = ValidationService()

    def test_detects_duplicate_slave_pins_in_master(self):
        s1 = _slave("s1", pin="7", led_count=0)
        s2 = _slave("s2", pin="7", led_count=0)
        master = _master(slaves={"s1": s1, "s2": s2})
        issues = self.service.validate({"m1": master})
        dups = [i for i in issues if i.category == "duplicate_slave_pin"]
        self.assertEqual(1, len(dups))
        self.assertEqual(SEVERITY_ERROR, dups[0].severity)
        self.assertEqual("masters.m1", dups[0].path)

    def test_no_duplicate_slave_pins_across_masters(self):
        s1 = _slave("s1", pin="7", led_count=0)
        s2 = _slave("s2", pin="7", led_count=0)
        m1 = _master("m1", ip="10.0.0.1", slaves={"s1": s1})
        m2 = _master("m2", ip="10.0.0.2", slaves={"s2": s2})
        issues = self.service.validate({"m1": m1, "m2": m2})
        self.assertFalse(any(i.category == "duplicate_slave_pin" for i in issues))


class ValidationServiceInvalidIpTests(unittest.TestCase):
    def setUp(self):
        self.service = ValidationService()

    def test_detects_invalid_ipv4_address(self):
        master = _master(ip="not.an.ip")
        issues = self.service.validate({"m1": master})
        bad = [i for i in issues if i.category == "invalid_ip"]
        self.assertEqual(1, len(bad))
        self.assertEqual(SEVERITY_ERROR, bad[0].severity)
        self.assertEqual("masters.m1", bad[0].path)

    def test_detects_empty_ip(self):
        master = _master(ip="")
        issues = self.service.validate({"m1": master})
        bad = [i for i in issues if i.category == "invalid_ip"]
        self.assertEqual(1, len(bad))

    def test_detects_ipv6_format(self):
        master = _master(ip="::1")
        issues = self.service.validate({"m1": master})
        bad = [i for i in issues if i.category == "invalid_ip"]
        self.assertEqual(1, len(bad))

    def test_accepts_valid_ipv4(self):
        master = _master(ip="10.0.0.1")
        issues = self.service.validate({"m1": master})
        self.assertFalse(any(i.category == "invalid_ip" for i in issues))


class ValidationServiceWarningsTests(unittest.TestCase):
    def setUp(self):
        self.service = ValidationService()

    def test_warning_for_gap_between_segments(self):
        t1 = _tag_type("a", "0", topology=[0, 1, 2])
        t2 = _tag_type("b", "5", topology=[0, 1, 2])
        slave = _slave(pin="0", led_count=10, tag_types={"a": t1, "b": t2})
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        gaps = [i for i in issues if i.category == "gap"]
        self.assertEqual(1, len(gaps))
        self.assertEqual(SEVERITY_WARNING, gaps[0].severity)

    def test_no_warning_for_contiguous_full_coverage(self):
        t1 = _tag_type("a", "0", topology=[0, 1, 2, 3, 4])
        t2 = _tag_type("b", "5", topology=[0, 1, 2, 3, 4])
        slave = _slave(pin="0", led_count=10, tag_types={"a": t1, "b": t2})
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        self.assertEqual([], issues)


class ValidationServicePathFormatTests(unittest.TestCase):
    def setUp(self):
        self.service = ValidationService()

    def test_issue_path_for_slave_level_check(self):
        t1 = _tag_type("a", "0", topology=[0, 1, 2, 3])
        t2 = _tag_type("b", "3", topology=[0, 1, 2])
        slave = _slave(pin="0", led_count=10, tag_types={"a": t1, "b": t2})
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        overlaps = [i for i in issues if i.category == "overlap"]
        self.assertEqual(1, len(overlaps))
        self.assertEqual("masters.m1.slaves.s1", overlaps[0].path)

    def test_issue_path_for_tag_type_level_check(self):
        tt = _tag_type("a", "8", topology=[0, 1, 2, 3])
        slave = _slave(pin="0", led_count=10, tag_types={"a": tt})
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        oob = [i for i in issues if i.category == "out_of_bounds"]
        self.assertEqual(1, len(oob))
        self.assertEqual(
            "masters.m1.slaves.s1.tag_types.a",
            oob[0].path,
        )

    def test_issue_path_for_master_level_check(self):
        s1 = _slave("s1", pin="7", led_count=0)
        s2 = _slave("s2", pin="7", led_count=0)
        master = _master(ip="not-an-ip", slaves={"s1": s1, "s2": s2})
        issues = self.service.validate({"m1": master})
        invalid_ip = [i for i in issues if i.category == "invalid_ip"]
        dup_pin = [i for i in issues if i.category == "duplicate_slave_pin"]
        self.assertEqual(1, len(invalid_ip))
        self.assertEqual(1, len(dup_pin))
        self.assertEqual("masters.m1", invalid_ip[0].path)
        self.assertEqual("masters.m1", dup_pin[0].path)


class ValidationIssueShapeTests(unittest.TestCase):
    def setUp(self):
        self.service = ValidationService()

    def test_issue_is_frozen_dataclass(self):
        issue = ValidationIssue(
            severity=SEVERITY_ERROR,
            category="overlap",
            path="masters.m1",
            message="x",
        )
        with self.assertRaises(Exception):  # noqa: B017 - frozen dataclass raises FrozenInstanceError; test only cares that assignment fails
            issue.severity = SEVERITY_WARNING

    def test_all_issue_fields_well_formed(self):
        t1 = _tag_type("a", "0", topology=[0, 1, 2, 3])
        t2 = _tag_type("b", "3", topology=[0, 1, 2])
        slave = _slave(pin="0", led_count=5, tag_types={"a": t1, "b": t2})
        master = _master(ip="not-an-ip", slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        self.assertGreater(len(issues), 0)
        for issue in issues:
            self.assertIsInstance(issue, ValidationIssue)
            self.assertIn(
                issue.severity,
                (SEVERITY_ERROR, SEVERITY_WARNING),
            )
            self.assertIsInstance(issue.category, str)
            self.assertTrue(issue.path.startswith("masters."))
            self.assertIsInstance(issue.message, str)


class ValidationServiceLedCellsTests(unittest.TestCase):
    def setUp(self):
        self.service = ValidationService()

    def test_led_cells_length_mismatch_raises_error(self):
        # led_count=4 but led_cells only provides 3 entries.
        slave = _slave(
            pin="0",
            led_count=4,
            grid_rows=2,
            grid_columns=2,
            led_cells=[0, 1, 2],
        )
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        mismatches = [i for i in issues if i.category == "led_cells_mismatch"]
        self.assertEqual(1, len(mismatches))
        self.assertEqual(SEVERITY_ERROR, mismatches[0].severity)
        self.assertEqual("masters.m1.slaves.s1", mismatches[0].path)

    def test_led_cells_duplicate_values_raises_error(self):
        slave = _slave(
            pin="0",
            led_count=3,
            grid_rows=2,
            grid_columns=2,
            led_cells=[0, 0, 1],
        )
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        dupes = [i for i in issues if i.category == "led_cells_duplicate"]
        self.assertEqual(1, len(dupes))
        self.assertEqual(SEVERITY_ERROR, dupes[0].severity)
        self.assertIn("0", dupes[0].message)

    def test_led_cells_out_of_canvas_raises_error(self):
        # Canvas 2x2=4, so valid cells are [0..3]. 4 is out of range.
        slave = _slave(
            pin="0",
            led_count=3,
            grid_rows=2,
            grid_columns=2,
            led_cells=[0, 1, 4],
        )
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        oor = [i for i in issues if i.category == "led_cells_out_of_canvas"]
        self.assertEqual(1, len(oor))
        self.assertEqual(SEVERITY_ERROR, oor[0].severity)
        self.assertIn("4", oor[0].message)

    def test_canvas_zero_dimensions_raises_error(self):
        slave = _slave(
            pin="0",
            led_count=0,
            grid_rows=0,
            grid_columns=0,
            led_cells=[],
        )
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        zero = [i for i in issues if i.category == "canvas_zero"]
        self.assertEqual(1, len(zero))
        self.assertEqual(SEVERITY_ERROR, zero[0].severity)

    def test_canvas_too_small_for_leds_raises_error(self):
        # Canvas 2x2=4 but led_count=5 > 4.
        slave = _slave(
            pin="0",
            led_count=5,
            grid_rows=2,
            grid_columns=2,
            led_cells=[0, 1, 2, 3, 0],
        )
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        too_small = [i for i in issues if i.category == "canvas_too_small_for_leds"]
        self.assertEqual(1, len(too_small))
        self.assertEqual(SEVERITY_ERROR, too_small[0].severity)

    def test_topology_references_non_led_cell_raises_error(self):
        # Canvas 2x2=4 with only cells 0 and 1 physically wired.
        # A TagType topology touching cell 2 (no LED) must error.
        tt = _tag_type("t", "0", topology=[0, 2])
        slave = _slave(
            pin="0",
            led_count=2,
            grid_rows=2,
            grid_columns=2,
            led_cells=[0, 1],
            tag_types={"t": tt},
        )
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        bad = [i for i in issues if i.category == "topology_non_led_cell"]
        self.assertEqual(1, len(bad))
        self.assertEqual(SEVERITY_ERROR, bad[0].severity)
        self.assertEqual(
            "masters.m1.slaves.s1.tag_types.t",
            bad[0].path,
        )

    def test_valid_slave_with_custom_led_cells_passes(self):
        # Non-sequential led_cells ordering must validate cleanly.
        slave = _slave(
            pin="0",
            led_count=4,
            grid_rows=2,
            grid_columns=2,
            led_cells=[3, 1, 0, 2],
        )
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        led_issues = [
            i
            for i in issues
            if i.category
            in {
                "led_cells_mismatch",
                "led_cells_duplicate",
                "led_cells_out_of_canvas",
                "canvas_zero",
                "canvas_too_small_for_leds",
            }
        ]
        self.assertEqual([], led_issues)

    def test_valid_slave_with_canvas_larger_than_leds_passes(self):
        # Canvas 4x4=16 but only 10 LEDs wired: the remaining 6
        # cells are empty placeholders, which is allowed.
        slave = _slave(
            pin="0",
            led_count=10,
            grid_rows=4,
            grid_columns=4,
            led_cells=list(range(10)),
        )
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        self.assertEqual([], issues)

    def test_default_sequential_led_cells_passes(self):
        # Migration default: led_cells = [0..led_count-1] on a
        # 1×N linear canvas must pass all invariants.
        slave = _slave(
            pin="0",
            led_count=30,
            grid_rows=1,
            grid_columns=30,
            led_cells=list(range(30)),
        )
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        self.assertEqual([], issues)

    def test_topology_in_led_cells_non_sequential_passes(self):
        # led_cells reorders the wire; topology references cell
        # indices on the canvas (not wire positions) — must pass.
        tt = _tag_type("t", "0", topology=[3, 1])
        slave = _slave(
            pin="0",
            led_count=4,
            grid_rows=2,
            grid_columns=2,
            led_cells=[3, 1, 0, 2],
            tag_types={"t": tt},
        )
        master = _master(slaves={"s1": slave})
        issues = self.service.validate({"m1": master})
        topo_issues = [i for i in issues if i.category == "topology_non_led_cell"]
        self.assertEqual([], topo_issues)


if __name__ == "__main__":
    unittest.main()
