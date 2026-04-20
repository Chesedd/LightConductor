import csv
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.score_export import (
    FIELD_ORDER,
    build_score_records,
    render_csv,
    render_json,
)
from lightconductor.domain.models import Master, Slave, Tag, TagType


def make_master(**kwargs):
    return Master(
        id=kwargs.get("id", "m1"),
        name=kwargs.get("name", "M"),
        ip=kwargs.get("ip", "192.168.0.10"),
        slaves=kwargs.get("slaves", {}),
    )


def make_slave(**kwargs):
    return Slave(
        id=kwargs.get("id", "s1"),
        name=kwargs.get("name", "S"),
        pin=kwargs.get("pin", "1"),
        led_count=kwargs.get("led_count", 4),
        tag_types=kwargs.get("tag_types", {}),
    )


def make_type(**kwargs):
    topology = kwargs.get("topology", [0])
    return TagType(
        name=kwargs.get("name", "alpha"),
        pin=kwargs.get("pin", "1"),
        rows=kwargs.get("rows", 1),
        columns=kwargs.get("columns", len(topology)),
        topology=topology,
        tags=kwargs.get("tags", []),
    )


class BuildScoreRecordsTests(unittest.TestCase):
    def test_empty_masters_returns_empty_list(self):
        self.assertEqual([], build_score_records({}))

    def test_master_with_no_slaves_returns_empty_list(self):
        master = make_master(slaves={})
        self.assertEqual([], build_score_records({"m1": master}))

    def test_slave_with_no_tag_types_returns_empty_list(self):
        slave = make_slave(tag_types={})
        master = make_master(slaves={"s1": slave})
        self.assertEqual([], build_score_records({"m1": master}))

    def test_tag_type_with_no_tags_returns_empty_list(self):
        tag_type = make_type(tags=[])
        slave = make_slave(tag_types={"alpha": tag_type})
        master = make_master(slaves={"s1": slave})
        self.assertEqual([], build_score_records({"m1": master}))

    def test_single_tag_produces_record_per_topology_entry(self):
        tag = Tag(
            time_seconds=1.0,
            action=True,
            colors=[[10, 20, 30], [40, 50, 60], [70, 80, 90]],
        )
        tag_type = make_type(topology=[0, 1, 2], tags=[tag])
        slave = make_slave(tag_types={"alpha": tag_type})
        master = make_master(slaves={"s1": slave})

        records = build_score_records({"m1": master})
        self.assertEqual(3, len(records))
        self.assertEqual(
            [0, 1, 2],
            [rec["led_physical_index"] for rec in records],
        )
        self.assertEqual(
            (10, 20, 30), (records[0]["r"], records[0]["g"], records[0]["b"])
        )
        self.assertEqual(
            (40, 50, 60), (records[1]["r"], records[1]["g"], records[1]["b"])
        )
        self.assertEqual(
            (70, 80, 90), (records[2]["r"], records[2]["g"], records[2]["b"])
        )

    def test_colors_shorter_than_topology_pads_black(self):
        tag = Tag(time_seconds=0.0, action=True, colors=[[255, 0, 0]])
        tag_type = make_type(topology=[0, 1, 2], tags=[tag])
        slave = make_slave(tag_types={"alpha": tag_type})
        master = make_master(slaves={"s1": slave})

        records = build_score_records({"m1": master})
        self.assertEqual(3, len(records))
        self.assertEqual(
            (255, 0, 0), (records[0]["r"], records[0]["g"], records[0]["b"])
        )
        self.assertEqual((0, 0, 0), (records[1]["r"], records[1]["g"], records[1]["b"]))
        self.assertEqual((0, 0, 0), (records[2]["r"], records[2]["g"], records[2]["b"]))
        self.assertTrue(all(rec["action"] is True for rec in records))

    def test_colors_longer_than_topology_truncated(self):
        tag = Tag(
            time_seconds=0.0,
            action=True,
            colors=[[255, 0, 0], [0, 255, 0]],
        )
        tag_type = make_type(topology=[0], tags=[tag])
        slave = make_slave(tag_types={"alpha": tag_type})
        master = make_master(slaves={"s1": slave})

        records = build_score_records({"m1": master})
        self.assertEqual(1, len(records))
        self.assertEqual(
            (255, 0, 0), (records[0]["r"], records[0]["g"], records[0]["b"])
        )

    def test_action_off_yields_false_in_records(self):
        tag = Tag(
            time_seconds=0.0,
            action=False,
            colors=[[100, 100, 100], [200, 200, 200]],
        )
        tag_type = make_type(topology=[0, 1], tags=[tag])
        slave = make_slave(tag_types={"alpha": tag_type})
        master = make_master(slaves={"s1": slave})

        records = build_score_records({"m1": master})
        self.assertEqual(2, len(records))
        self.assertTrue(all(rec["action"] is False for rec in records))

    def test_string_action_on_becomes_boolean_true(self):
        tag = Tag(time_seconds=0.0, action="On", colors=[[1, 2, 3]])
        tag_type = make_type(topology=[0], tags=[tag])
        slave = make_slave(tag_types={"alpha": tag_type})
        master = make_master(slaves={"s1": slave})

        records = build_score_records({"m1": master})
        self.assertEqual(1, len(records))
        self.assertIs(True, records[0]["action"])

    def test_records_sorted_by_time_then_master_slave_pin_led(self):
        # Two masters inserted in order m2, m1.
        m2_tag_type = make_type(
            name="alpha",
            pin="1",
            topology=[0],
            tags=[
                Tag(time_seconds=2.0, action=True, colors=[[1, 1, 1]]),
                Tag(time_seconds=1.0, action=True, colors=[[2, 2, 2]]),
            ],
        )
        m1_tag_type = make_type(
            name="alpha",
            pin="1",
            topology=[0],
            tags=[
                Tag(time_seconds=1.0, action=True, colors=[[3, 3, 3]]),
                Tag(time_seconds=2.0, action=True, colors=[[4, 4, 4]]),
            ],
        )
        m2 = make_master(
            id="m2",
            name="M2",
            slaves={
                "s1": make_slave(
                    id="s1",
                    tag_types={"alpha": m2_tag_type},
                ),
            },
        )
        m1 = make_master(
            id="m1",
            name="M1",
            slaves={
                "s1": make_slave(
                    id="s1",
                    tag_types={"alpha": m1_tag_type},
                ),
            },
        )

        # Insertion order m2 first, m1 second — sort must reorder.
        records = build_score_records({"m2": m2, "m1": m1})
        self.assertEqual(4, len(records))

        self.assertEqual(1.0, records[0]["time_seconds"])
        self.assertEqual("m1", records[0]["master_id"])
        self.assertEqual(1.0, records[1]["time_seconds"])
        self.assertEqual("m2", records[1]["master_id"])
        self.assertEqual(2.0, records[2]["time_seconds"])
        self.assertEqual("m1", records[2]["master_id"])
        self.assertEqual(2.0, records[3]["time_seconds"])
        self.assertEqual("m2", records[3]["master_id"])

    def test_color_string_format_normalized(self):
        tag = Tag(time_seconds=0.0, action=True, colors=["255,0,128"])
        tag_type = make_type(topology=[0], tags=[tag])
        slave = make_slave(tag_types={"alpha": tag_type})
        master = make_master(slaves={"s1": slave})

        records = build_score_records({"m1": master})
        self.assertEqual(1, len(records))
        self.assertEqual(
            (255, 0, 128), (records[0]["r"], records[0]["g"], records[0]["b"])
        )

    def test_color_out_of_range_clamped(self):
        tag = Tag(time_seconds=0.0, action=True, colors=[[300, -5, 128]])
        tag_type = make_type(topology=[0], tags=[tag])
        slave = make_slave(tag_types={"alpha": tag_type})
        master = make_master(slaves={"s1": slave})

        records = build_score_records({"m1": master})
        self.assertEqual(1, len(records))
        self.assertEqual(
            (255, 0, 128), (records[0]["r"], records[0]["g"], records[0]["b"])
        )


class RenderCsvTests(unittest.TestCase):
    def test_csv_has_header_row(self):
        output = render_csv([])
        lines = output.splitlines()
        self.assertEqual(1, len(lines))
        self.assertEqual(",".join(FIELD_ORDER), lines[0])

    def test_csv_action_rendered_as_on_off(self):
        records = [
            {
                "time_seconds": 0.0,
                "master_id": "m1",
                "master_name": "M",
                "master_ip": "ip",
                "slave_id": "s1",
                "slave_name": "S",
                "slave_pin": "1",
                "type_name": "alpha",
                "type_pin": 1,
                "led_physical_index": 0,
                "action": True,
                "r": 10,
                "g": 20,
                "b": 30,
            },
            {
                "time_seconds": 1.0,
                "master_id": "m1",
                "master_name": "M",
                "master_ip": "ip",
                "slave_id": "s1",
                "slave_name": "S",
                "slave_pin": "1",
                "type_name": "alpha",
                "type_pin": 1,
                "led_physical_index": 0,
                "action": False,
                "r": 0,
                "g": 0,
                "b": 0,
            },
        ]
        output = render_csv(records)
        rows = list(csv.reader(io.StringIO(output)))
        # rows[0] is header; rows[1] first data row; rows[2] second.
        action_idx = FIELD_ORDER.index("action")
        self.assertEqual("On", rows[1][action_idx])
        self.assertEqual("Off", rows[2][action_idx])


class RenderJsonTests(unittest.TestCase):
    def test_json_action_rendered_as_boolean(self):
        records = [
            {
                "time_seconds": 0.0,
                "master_id": "m1",
                "master_name": "M",
                "master_ip": "ip",
                "slave_id": "s1",
                "slave_name": "S",
                "slave_pin": "1",
                "type_name": "alpha",
                "type_pin": 1,
                "led_physical_index": 0,
                "action": True,
                "r": 10,
                "g": 20,
                "b": 30,
            },
            {
                "time_seconds": 1.0,
                "master_id": "m1",
                "master_name": "M",
                "master_ip": "ip",
                "slave_id": "s1",
                "slave_name": "S",
                "slave_pin": "1",
                "type_name": "alpha",
                "type_pin": 1,
                "led_physical_index": 0,
                "action": False,
                "r": 0,
                "g": 0,
                "b": 0,
            },
        ]
        output = render_json(records)
        parsed = json.loads(output)
        self.assertIsInstance(parsed, list)
        self.assertEqual(2, len(parsed))
        self.assertIs(True, parsed[0]["action"])
        self.assertIs(False, parsed[1]["action"])

    def test_json_empty_records_is_empty_array(self):
        parsed = json.loads(render_json([]))
        self.assertIsInstance(parsed, list)
        self.assertEqual(0, len(parsed))


if __name__ == "__main__":
    unittest.main()
