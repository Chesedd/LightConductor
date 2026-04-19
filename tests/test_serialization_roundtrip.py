"""Round-trip serialization coverage for pack_* / unpack_* in
json_mapper.

Replaces the ProjectManager-based test suite from PR #5 after
ProjectManager was removed in Phase 1.2.2b. Semantics are
identical: build a domain tree, pack to dict, unpack back,
pack again, assert pack1 == pack2 ('double pack' invariant).
This pattern is insensitive to format quirks (segment_start
derived from pin, segment_size derived from topology).
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.domain.models import Master, Slave, Tag, TagType
from lightconductor.infrastructure.json_mapper import (
    pack_master, unpack_master,
)


def _pack_project(masters):
    return {
        master_id: pack_master(m)
        for master_id, m in masters.items()
    }


def _unpack_project(boxes):
    return {
        master_id: unpack_master(m_dict)
        for master_id, m_dict in boxes.items()
    }


def _round_trip(masters):
    packed_once = _pack_project(masters)
    unpacked = _unpack_project(packed_once)
    packed_twice = _pack_project(unpacked)
    return packed_once, packed_twice


class SerializationRoundTripTests(unittest.TestCase):

    def test_empty_project_roundtrip(self):
        packed_once, packed_twice = _round_trip({})
        self.assertEqual(packed_once, packed_twice)

    def test_master_without_slaves(self):
        masters = {
            "m1": Master(id="m1", name="M", ip="1.2.3.4", slaves={}),
        }
        packed_once, packed_twice = _round_trip(masters)
        self.assertEqual(packed_once, packed_twice)

    def test_slave_without_tag_types(self):
        masters = {
            "m1": Master(
                id="m1", name="M", ip="1.2.3.4",
                slaves={
                    "s1": Slave(id="s1", name="S", pin="7",
                                led_count=60, tag_types={}),
                },
            ),
        }
        packed_once, packed_twice = _round_trip(masters)
        self.assertEqual(packed_once, packed_twice)

    def test_type_without_tags(self):
        masters = {
            "m1": Master(
                id="m1", name="M", ip="1.2.3.4",
                slaves={
                    "s1": Slave(
                        id="s1", name="S", pin="7", led_count=60,
                        tag_types={
                            "front": TagType(
                                name="front", pin="3",
                                rows=1, columns=4,
                                color="255,0,0",
                                topology=[0, 1, 2, 3], tags=[]),
                        },
                    ),
                },
            ),
        }
        packed_once, packed_twice = _round_trip(masters)
        self.assertEqual(packed_once, packed_twice)

    def test_minimal_full_project(self):
        masters = {
            "m1": Master(
                id="m1", name="M", ip="1.2.3.4",
                slaves={
                    "s1": Slave(
                        id="s1", name="S", pin="7", led_count=60,
                        tag_types={
                            "front": TagType(
                                name="front", pin="3",
                                rows=1, columns=4,
                                color="255,0,0",
                                topology=[0, 1, 2, 3],
                                tags=[Tag(time_seconds=0.5,
                                          action=True,
                                          colors=[[1, 2, 3]])]),
                        },
                    ),
                },
            ),
        }
        packed_once, packed_twice = _round_trip(masters)
        self.assertEqual(packed_once, packed_twice)

    def test_multi_level_project(self):
        masters = {
            "m1": Master(
                id="m1", name="Room A", ip="10.0.0.1",
                slaves={
                    "s1": Slave(
                        id="s1", name="Front", pin="1", led_count=60,
                        tag_types={
                            "red": TagType(
                                name="red", pin="1", rows=1, columns=2,
                                color=[255, 0, 0], topology=[0, 1],
                                tags=[
                                    Tag(time_seconds=0.1, action=True,
                                        colors=[[255, 0, 0]]),
                                    Tag(time_seconds=0.2, action=False,
                                        colors=[[0, 255, 0]]),
                                ],
                            ),
                            "blue": TagType(
                                name="blue", pin="2", rows=1, columns=3,
                                color=[0, 0, 255], topology=[2, 3, 4],
                                tags=[
                                    Tag(time_seconds=0.3, action=True,
                                        colors=[[0, 0, 255]]),
                                ],
                            ),
                        },
                    ),
                    "s2": Slave(
                        id="s2", name="Back", pin="2", led_count=120,
                        tag_types={
                            "green": TagType(
                                name="green", pin="3", rows=1, columns=1,
                                color=[0, 255, 0], topology=[5],
                                tags=[
                                    Tag(time_seconds=0.4, action=False,
                                        colors=[[0, 255, 0]]),
                                    Tag(time_seconds=0.5, action=True,
                                        colors=[[0, 255, 0]]),
                                    Tag(time_seconds=0.6, action=False,
                                        colors=[[0, 255, 0]]),
                                ],
                            ),
                        },
                    ),
                },
            ),
            "m2": Master(
                id="m2", name="Room B", ip="10.0.0.2",
                slaves={
                    "s3": Slave(
                        id="s3", name="Only", pin="5", led_count=30,
                        tag_types={},
                    ),
                },
            ),
        }
        packed_once, packed_twice = _round_trip(masters)
        self.assertEqual(packed_once, packed_twice)

    def test_unicode_in_names(self):
        masters = {
            "m1": Master(
                id="m1", name="Мастер 🎨", ip="1.2.3.4",
                slaves={
                    "s1": Slave(
                        id="s1", name="一号", pin="1", led_count=60,
                        tag_types={
                            "красный": TagType(
                                name="красный", pin="1",
                                rows=1, columns=1,
                                color=[255, 0, 0],
                                topology=[0],
                                tags=[],
                            ),
                        },
                    ),
                },
            ),
        }
        packed_once, packed_twice = _round_trip(masters)
        self.assertEqual(packed_once, packed_twice)

    def test_numeric_pin_preserved(self):
        # str pin -> str
        masters_str = {
            "m1": Master(
                id="m1", name="M", ip="1.2.3.4",
                slaves={
                    "s1": Slave(
                        id="s1", name="S", pin="7", led_count=60,
                        tag_types={
                            "red": TagType(
                                name="red", pin="3",
                                rows=1, columns=3,
                                color="r", topology=[0, 1, 2],
                                tags=[],
                            ),
                        },
                    ),
                },
            ),
        }
        packed_once, packed_twice = _round_trip(masters_str)
        self.assertEqual(packed_once, packed_twice)
        pin_val = packed_once["m1"]["slaves"]["s1"]["tagTypes"]["red"]["pin"]
        self.assertEqual(pin_val, "3")
        self.assertIsInstance(pin_val, str)

        # int pin -> int (dataclass does not coerce, mapper does not coerce)
        tt_int = TagType.__new__(TagType)
        tt_int.name = "red"
        tt_int.pin = 3
        tt_int.rows = 1
        tt_int.columns = 3
        tt_int.color = "r"
        tt_int.topology = [0, 1, 2]
        tt_int.tags = []
        masters_int = {
            "m1": Master(
                id="m1", name="M", ip="1.2.3.4",
                slaves={
                    "s1": Slave(
                        id="s1", name="S", pin="7", led_count=60,
                        tag_types={"red": tt_int},
                    ),
                },
            ),
        }
        packed_once_int = _pack_project(masters_int)
        pin_val_int = packed_once_int["m1"]["slaves"]["s1"]["tagTypes"]["red"]["pin"]
        self.assertEqual(pin_val_int, 3)
        self.assertIsInstance(pin_val_int, int)

    def test_topology_order_preserved(self):
        masters = {
            "m1": Master(
                id="m1", name="M", ip="1.2.3.4",
                slaves={
                    "s1": Slave(
                        id="s1", name="S", pin="7", led_count=60,
                        tag_types={
                            "red": TagType(
                                name="red", pin="3",
                                rows=1, columns=4,
                                color="r", topology=[3, 1, 0, 2],
                                tags=[],
                            ),
                        },
                    ),
                },
            ),
        }
        packed_once, packed_twice = _round_trip(masters)
        self.assertEqual(packed_once, packed_twice)
        self.assertEqual(
            packed_once["m1"]["slaves"]["s1"]["tagTypes"]["red"]["topology"],
            [3, 1, 0, 2],
        )

    def test_multiple_colors_per_tag(self):
        masters = {
            "m1": Master(
                id="m1", name="M", ip="1.2.3.4",
                slaves={
                    "s1": Slave(
                        id="s1", name="S", pin="7", led_count=60,
                        tag_types={
                            "red": TagType(
                                name="red", pin="3",
                                rows=1, columns=1,
                                color="r", topology=[0],
                                tags=[
                                    Tag(time_seconds=0.1, action=True,
                                        colors=[[255, 0, 0],
                                                [0, 255, 0],
                                                [0, 0, 255]]),
                                ],
                            ),
                        },
                    ),
                },
            ),
        }
        packed_once, packed_twice = _round_trip(masters)
        self.assertEqual(packed_once, packed_twice)
        self.assertEqual(
            packed_once["m1"]["slaves"]["s1"]["tagTypes"]["red"]["tags"][0]["colors"],
            [[255, 0, 0], [0, 255, 0], [0, 0, 255]],
        )

    def test_master_with_default_ip(self):
        masters = {
            "x": Master(id="x", name="x", slaves={}),
        }
        packed_once, packed_twice = _round_trip(masters)
        self.assertEqual(packed_once, packed_twice)
        self.assertEqual(packed_once["x"]["ip"], "192.168.0.129")


if __name__ == "__main__":
    unittest.main()
