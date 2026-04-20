import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lightconductor.domain.models import Master, Slave, Tag, TagType
from lightconductor.infrastructure.json_mapper import (
    pack_master,
    pack_slave,
    pack_tag,
    pack_tag_type,
    unpack_master,
    unpack_slave,
    unpack_tag,
    unpack_tag_type,
)


class PackTagTests(unittest.TestCase):
    def test_pack_tag_minimal_fields(self):
        tag = Tag(time_seconds=0.5, action=True, colors=[[255, 0, 0]])
        self.assertEqual(
            pack_tag(tag),
            {"time": 0.5, "action": True, "colors": [[255, 0, 0]]},
        )

    def test_pack_tag_with_string_action(self):
        tag = Tag(time_seconds=2.0, action="toggle", colors=[[0, 0, 0]])
        packed = pack_tag(tag)
        self.assertEqual(packed["action"], "toggle")
        self.assertIsInstance(packed["action"], str)

    def test_pack_tag_with_empty_colors(self):
        tag = Tag(time_seconds=0.0, action=False, colors=[])
        packed = pack_tag(tag)
        self.assertEqual(packed["colors"], [])

    def test_pack_tag_preserves_int_time(self):
        # time_seconds is type-annotated as float, but dataclass does not
        # validate, and the mapper must not coerce. An int in => an int out.
        tag = Tag(time_seconds=1, action=True, colors=[])
        packed = pack_tag(tag)
        self.assertEqual(packed["time"], 1)
        self.assertIsInstance(packed["time"], int)


class UnpackTagTests(unittest.TestCase):
    def test_unpack_tag_builds_domain_object(self):
        data = {"time": 0.5, "action": True, "colors": [[1, 2, 3]]}
        tag = unpack_tag(data)
        self.assertIsInstance(tag, Tag)
        self.assertEqual(tag.time_seconds, 0.5)
        self.assertIs(tag.action, True)
        self.assertEqual(tag.colors, [[1, 2, 3]])

    def test_unpack_tag_rejects_non_dict(self):
        with self.assertRaises(ValueError) as ctx:
            unpack_tag([1, 2])
        message = str(ctx.exception)
        self.assertIn("tag", message)
        self.assertIn("dict", message)

    def test_unpack_tag_rejects_missing_fields(self):
        data = {"time": 0.5}  # missing action + colors
        with self.assertRaises(ValueError) as ctx:
            unpack_tag(data)
        message = str(ctx.exception)
        self.assertIn("action", message)
        self.assertIn("colors", message)


class RoundTripTests(unittest.TestCase):
    def test_roundtrip_pack_then_unpack(self):
        tag_in = Tag(time_seconds=0.25, action=False, colors=[[10, 20, 30]])
        tag_out = unpack_tag(pack_tag(tag_in))
        self.assertEqual(tag_out, tag_in)


class PackTagTypeTests(unittest.TestCase):
    def test_pack_tag_type_without_tags(self):
        tt = TagType(
            name="front",
            pin="3",
            rows=2,
            columns=3,
            color=[10, 20, 30],
            topology=[0, 1, 2, 3, 4, 5],
            tags=[],
        )
        result = pack_tag_type(tt)
        self.assertEqual(
            set(result.keys()),
            {
                "color",
                "pin",
                "segment_start",
                "segment_size",
                "row",
                "table",
                "topology",
                "tags",
            },
        )
        self.assertEqual(result["color"], [10, 20, 30])
        self.assertEqual(result["pin"], "3")
        self.assertEqual(result["row"], 2)
        self.assertEqual(result["table"], 3)
        self.assertEqual(result["topology"], [0, 1, 2, 3, 4, 5])
        self.assertEqual(result["tags"], {})

    def test_pack_tag_type_segment_start_mirrors_pin(self):
        tt_str = TagType(
            name="x",
            pin="7",
            rows=1,
            columns=1,
            color="r",
            topology=[0],
            tags=[],
        )
        self.assertEqual(pack_tag_type(tt_str)["segment_start"], "7")

        tt_int = TagType(
            name="x",
            pin=5,
            rows=1,
            columns=1,
            color="r",
            topology=[0],
            tags=[],
        )
        packed_int = pack_tag_type(tt_int)
        self.assertEqual(packed_int["segment_start"], 5)
        self.assertIsInstance(packed_int["segment_start"], int)

    def test_pack_tag_type_segment_size_equals_topology_length(self):
        tt_five = TagType(
            name="x",
            pin="1",
            rows=1,
            columns=1,
            color="r",
            topology=[0, 1, 2, 3, 4],
            tags=[],
        )
        self.assertEqual(pack_tag_type(tt_five)["segment_size"], 5)

        tt_empty = TagType(
            name="x",
            pin="1",
            rows=1,
            columns=1,
            color="r",
            topology=[],
            tags=[],
        )
        self.assertEqual(pack_tag_type(tt_empty)["segment_size"], 0)

    def test_pack_tag_type_rows_becomes_row(self):
        tt = TagType(
            name="x",
            pin="1",
            rows=4,
            columns=1,
            color="r",
            topology=[0],
            tags=[],
        )
        self.assertEqual(pack_tag_type(tt)["row"], 4)

    def test_pack_tag_type_columns_becomes_table(self):
        tt = TagType(
            name="x",
            pin="1",
            rows=1,
            columns=8,
            color="r",
            topology=[0],
            tags=[],
        )
        self.assertEqual(pack_tag_type(tt)["table"], 8)

    def test_pack_tag_type_with_tags_uses_int_keys(self):
        tt = TagType(
            name="x",
            pin="1",
            rows=1,
            columns=1,
            color="r",
            topology=[0],
            tags=[
                Tag(time_seconds=0.1, action=True, colors=[[1, 0, 0]]),
                Tag(time_seconds=0.2, action=False, colors=[[0, 1, 0]]),
            ],
        )
        result = pack_tag_type(tt)
        self.assertEqual(set(result["tags"]), {0, 1})
        self.assertEqual(result["tags"][0], pack_tag(tt.tags[0]))
        self.assertEqual(result["tags"][1], pack_tag(tt.tags[1]))

    def test_pack_tag_type_name_not_in_dict(self):
        tt = TagType(
            name="exclusive_name",
            pin="1",
            rows=1,
            columns=1,
            color="x",
            topology=[0],
            tags=[],
        )
        result = pack_tag_type(tt)
        self.assertNotIn("name", result)


class UnpackTagTypeTests(unittest.TestCase):
    def test_unpack_tag_type_builds_domain_with_name(self):
        data = {
            "color": [1, 2, 3],
            "pin": "4",
            "segment_start": "4",
            "segment_size": 3,
            "row": 2,
            "table": 2,
            "topology": [0, 1, 2],
            "tags": {},
        }
        tt = unpack_tag_type(data, name="given_name")
        self.assertIsInstance(tt, TagType)
        self.assertEqual(tt.name, "given_name")
        self.assertEqual(tt.pin, "4")
        self.assertEqual(tt.rows, 2)
        self.assertEqual(tt.columns, 2)
        self.assertEqual(tt.color, [1, 2, 3])
        self.assertEqual(tt.topology, [0, 1, 2])
        self.assertEqual(tt.tags, [])

    def test_unpack_tag_type_ignores_segment_start_and_segment_size(self):
        data = {
            "color": "red",
            "pin": "9",
            "segment_start": "OTHER",
            "segment_size": 999,
            "row": 1,
            "table": 1,
            "topology": [0],
            "tags": {},
        }
        tt = unpack_tag_type(data, name="t")
        self.assertEqual(tt.pin, "9")
        # segment_size==999 did not leak into any domain attribute.
        self.assertEqual(tt.topology, [0])

    def test_unpack_tag_type_sorts_tag_keys_numerically(self):
        data = {
            "color": "x",
            "pin": "1",
            "segment_start": "1",
            "segment_size": 1,
            "row": 1,
            "table": 1,
            "topology": [0],
            "tags": {
                "10": {"time": 1.0, "action": True, "colors": []},
                "2": {"time": 0.2, "action": False, "colors": []},
                "1": {"time": 0.1, "action": True, "colors": []},
            },
        }
        tt = unpack_tag_type(data, name="t")
        self.assertEqual(
            [t.time_seconds for t in tt.tags],
            [0.1, 0.2, 1.0],
        )

    def test_unpack_tag_type_accepts_int_keys_in_tags(self):
        data = {
            "color": "x",
            "pin": "1",
            "segment_start": "1",
            "segment_size": 1,
            "row": 1,
            "table": 1,
            "topology": [0],
            "tags": {
                0: {"time": 0.0, "action": True, "colors": []},
                1: {"time": 0.1, "action": True, "colors": []},
            },
        }
        tt = unpack_tag_type(data, name="t")
        self.assertEqual(len(tt.tags), 2)
        self.assertEqual(tt.tags[0].time_seconds, 0.0)
        self.assertEqual(tt.tags[1].time_seconds, 0.1)

    def test_unpack_tag_type_rejects_non_dict(self):
        with self.assertRaises(ValueError) as ctx:
            unpack_tag_type(["not", "a", "dict"], name="x")
        message = str(ctx.exception)
        self.assertIn("tag_type", message)
        self.assertIn("dict", message)

    def test_unpack_tag_type_rejects_missing_fields(self):
        data = {"color": "r", "pin": "1"}
        with self.assertRaises(ValueError) as ctx:
            unpack_tag_type(data, name="x")
        message = str(ctx.exception)
        self.assertIn("row", message)
        self.assertIn("tags", message)

    def test_unpack_tag_type_rejects_non_integer_tag_keys(self):
        data = {
            "color": "x",
            "pin": "1",
            "segment_start": "1",
            "segment_size": 1,
            "row": 1,
            "table": 1,
            "topology": [0],
            "tags": {
                "not_an_int": {"time": 0.0, "action": True, "colors": []},
                "0": {"time": 0.1, "action": True, "colors": []},
            },
        }
        with self.assertRaises(ValueError) as ctx:
            unpack_tag_type(data, name="x")
        self.assertIn("non-integer key", str(ctx.exception))


class TagTypeRoundTripTests(unittest.TestCase):
    def test_roundtrip_pack_then_unpack_tag_type(self):
        tt_in = TagType(
            name="rt",
            pin="5",
            rows=2,
            columns=3,
            color=[100, 0, 0],
            topology=[2, 1, 0, 3, 4, 5],
            tags=[
                Tag(
                    time_seconds=0.5,
                    action=True,
                    colors=[[1, 2, 3]],
                )
            ],
        )
        packed = pack_tag_type(tt_in)
        tt_out = unpack_tag_type(packed, name="rt")
        self.assertEqual(tt_out, tt_in)


class PackSlaveTests(unittest.TestCase):
    def test_pack_slave_minimal_without_tag_types(self):
        s = Slave(id="s1", name="Front", pin="7", led_count=60, tag_types={})
        self.assertEqual(
            pack_slave(s),
            {
                "name": "Front",
                "pin": "7",
                "led_count": 60,
                "id": "s1",
                "tagTypes": {},
            },
        )

    def test_pack_slave_key_order_matches_spec(self):
        result = pack_slave(Slave(id="x", name="x", pin="0", led_count=0, tag_types={}))
        self.assertEqual(
            list(result.keys()),
            ["name", "pin", "led_count", "id", "tagTypes"],
        )

    def test_pack_slave_tag_types_becomes_tagTypes(self):
        # Q1: snake_case field on the domain object maps to a
        # camelCase key in the JSON dict.
        s = Slave(
            id="x",
            name="x",
            pin="0",
            led_count=0,
            tag_types={
                "front": TagType(
                    name="front",
                    pin="1",
                    rows=1,
                    columns=1,
                    color="r",
                    topology=[0],
                    tags=[],
                ),
            },
        )
        result = pack_slave(s)
        self.assertIn("tagTypes", result)
        self.assertNotIn("tag_types", result)
        self.assertIn("front", result["tagTypes"])

    def test_pack_slave_passthrough_pin_int(self):
        # Even though Slave.pin is annotated as str, the dataclass
        # accepts int without coercion. The mapper must write the int
        # through unchanged.
        s = Slave.__new__(Slave)
        s.id = "x"
        s.name = "x"
        s.pin = 7
        s.led_count = 0
        s.tag_types = {}
        result = pack_slave(s)
        self.assertEqual(result["pin"], 7)
        self.assertIsInstance(result["pin"], int)

    def test_pack_slave_passthrough_pin_str(self):
        s = Slave(id="x", name="x", pin="7", led_count=0, tag_types={})
        result = pack_slave(s)
        self.assertEqual(result["pin"], "7")
        self.assertIsInstance(result["pin"], str)

    def test_pack_slave_delegates_to_pack_tag_type(self):
        tt = TagType(
            name="front",
            pin="1",
            rows=2,
            columns=2,
            color=[10, 20, 30],
            topology=[0, 1, 2, 3],
            tags=[Tag(time_seconds=0.1, action=True, colors=[[1, 2, 3]])],
        )
        s = Slave(
            id="x",
            name="x",
            pin="0",
            led_count=0,
            tag_types={"front": tt},
        )
        result = pack_slave(s)
        self.assertEqual(result["tagTypes"]["front"], pack_tag_type(tt))


class UnpackSlaveTests(unittest.TestCase):
    def test_unpack_slave_builds_domain_object(self):
        data = {
            "name": "Front",
            "pin": "7",
            "led_count": 60,
            "id": "s1",
            "tagTypes": {},
        }
        s = unpack_slave(data)
        self.assertIsInstance(s, Slave)
        self.assertEqual(s.id, "s1")
        self.assertEqual(s.name, "Front")
        self.assertEqual(s.pin, "7")
        self.assertEqual(s.led_count, 60)
        self.assertEqual(s.tag_types, {})

    def test_unpack_slave_recurses_into_tag_types(self):
        data = {
            "name": "x",
            "pin": "0",
            "led_count": 0,
            "id": "x",
            "tagTypes": {
                "front": {
                    "color": "red",
                    "pin": "3",
                    "segment_start": "3",
                    "segment_size": 1,
                    "row": 1,
                    "table": 1,
                    "topology": [0],
                    "tags": {},
                },
            },
        }
        s = unpack_slave(data)
        self.assertIn("front", s.tag_types)
        self.assertIsInstance(s.tag_types["front"], TagType)
        # Name comes from the enclosing dict key, not from any
        # field inside `data["tagTypes"]["front"]`.
        self.assertEqual(s.tag_types["front"].name, "front")

    def test_unpack_slave_rejects_non_dict(self):
        with self.assertRaises(ValueError) as ctx:
            unpack_slave("not a dict")
        message = str(ctx.exception)
        self.assertIn("slave", message)
        self.assertIn("dict", message)

    def test_unpack_slave_rejects_missing_fields(self):
        data = {"name": "x"}
        with self.assertRaises(ValueError) as ctx:
            unpack_slave(data)
        message = str(ctx.exception)
        self.assertIn("pin", message)
        self.assertIn("led_count", message)
        self.assertIn("id", message)
        self.assertIn("tagTypes", message)

    def test_unpack_slave_rejects_non_dict_tagTypes(self):
        data = {
            "name": "x",
            "pin": "0",
            "led_count": 0,
            "id": "x",
            "tagTypes": ["not", "dict"],
        }
        with self.assertRaises(ValueError) as ctx:
            unpack_slave(data)
        self.assertIn("slave.tagTypes", str(ctx.exception))

    def test_unpack_slave_does_not_use_led_count_default(self):
        # led_count has default=0 on the dataclass, but in JSON the
        # field is mandatory: missing led_count must raise, not
        # silently default to 0.
        data = {"name": "x", "pin": "0", "id": "x", "tagTypes": {}}
        with self.assertRaises(ValueError) as ctx:
            unpack_slave(data)
        self.assertIn("led_count", str(ctx.exception))


class SlaveRoundTripTests(unittest.TestCase):
    def test_roundtrip_pack_then_unpack_slave(self):
        s_in = Slave(
            id="s1",
            name="Front Bar",
            pin="7",
            led_count=120,
            tag_types={
                "a": TagType(
                    name="a",
                    pin="1",
                    rows=1,
                    columns=2,
                    color=[255, 0, 0],
                    topology=[0, 1],
                    tags=[
                        Tag(
                            time_seconds=0.5,
                            action=True,
                            colors=[[1, 1, 1]],
                        )
                    ],
                ),
                "b": TagType(
                    name="b",
                    pin="3",
                    rows=2,
                    columns=2,
                    color="blue",
                    topology=[0, 1, 2, 3],
                    tags=[],
                ),
            },
        )
        s_out = unpack_slave(pack_slave(s_in))
        self.assertEqual(s_out, s_in)


class PackMasterTests(unittest.TestCase):
    def test_pack_master_minimal_without_slaves(self):
        m = Master(id="m1", name="Room A", ip="10.0.0.5", slaves={})
        self.assertEqual(
            pack_master(m),
            {
                "name": "Room A",
                "id": "m1",
                "ip": "10.0.0.5",
                "slaves": {},
            },
        )

    def test_pack_master_key_order_matches_spec(self):
        result = pack_master(Master(id="x", name="x", ip="x", slaves={}))
        self.assertEqual(
            list(result.keys()),
            ["name", "id", "ip", "slaves"],
        )

    def test_pack_master_ip_passthrough(self):
        # Any string is accepted in .ip; the mapper does not normalize
        # or validate the format.
        m = Master(id="x", name="x", ip="not.an.ip", slaves={})
        self.assertEqual(pack_master(m)["ip"], "not.an.ip")

    def test_pack_master_delegates_to_pack_slave(self):
        s = Slave(
            id="s1",
            name="Front",
            pin="7",
            led_count=60,
            tag_types={},
        )
        m = Master(
            id="m1",
            name="Room",
            ip="10.0.0.5",
            slaves={"s1": s},
        )
        result = pack_master(m)
        self.assertEqual(result["slaves"]["s1"], pack_slave(s))

    def test_pack_master_preserves_domain_default_ip(self):
        # Domain.Master default ip = "192.168.0.129". pack writes as-is.
        m = Master(id="x", name="x", slaves={})  # ip defaults
        self.assertEqual(pack_master(m)["ip"], "192.168.0.129")


class UnpackMasterTests(unittest.TestCase):
    def test_unpack_master_builds_domain_object(self):
        data = {
            "name": "Room A",
            "id": "m1",
            "ip": "10.0.0.5",
            "slaves": {},
        }
        m = unpack_master(data)
        self.assertIsInstance(m, Master)
        self.assertEqual(m.id, "m1")
        self.assertEqual(m.name, "Room A")
        self.assertEqual(m.ip, "10.0.0.5")
        self.assertEqual(m.slaves, {})

    def test_unpack_master_recurses_into_slaves(self):
        data = {
            "name": "x",
            "id": "x",
            "ip": "0.0.0.0",
            "slaves": {
                "s1": {
                    "name": "Front",
                    "pin": "7",
                    "led_count": 60,
                    "id": "s1",
                    "tagTypes": {},
                },
            },
        }
        m = unpack_master(data)
        self.assertIn("s1", m.slaves)
        self.assertIsInstance(m.slaves["s1"], Slave)
        self.assertEqual(m.slaves["s1"].name, "Front")

    def test_unpack_master_rejects_non_dict(self):
        with self.assertRaises(ValueError) as ctx:
            unpack_master("nope")
        message = str(ctx.exception)
        self.assertIn("master", message)
        self.assertIn("dict", message)

    def test_unpack_master_rejects_missing_fields(self):
        data = {"name": "x"}
        with self.assertRaises(ValueError) as ctx:
            unpack_master(data)
        message = str(ctx.exception)
        self.assertIn("id", message)
        self.assertIn("ip", message)
        self.assertIn("slaves", message)

    def test_unpack_master_rejects_non_dict_slaves(self):
        data = {"name": "x", "id": "x", "ip": "x", "slaves": []}
        with self.assertRaises(ValueError) as ctx:
            unpack_master(data)
        self.assertIn("master.slaves", str(ctx.exception))

    def test_unpack_master_does_not_use_ip_default(self):
        # Domain default ip must not apply on the unpack side.
        data = {"name": "x", "id": "x", "slaves": {}}
        with self.assertRaises(ValueError) as ctx:
            unpack_master(data)
        self.assertIn("ip", str(ctx.exception))


class MasterRoundTripTests(unittest.TestCase):
    def test_roundtrip_pack_then_unpack_master(self):
        m_in = Master(
            id="room-a",
            name="Room A",
            ip="192.168.1.200",
            slaves={
                "s1": Slave(
                    id="s1",
                    name="Front",
                    pin="7",
                    led_count=120,
                    tag_types={
                        "front": TagType(
                            name="front",
                            pin="3",
                            rows=1,
                            columns=4,
                            color=[255, 0, 0],
                            topology=[0, 1, 2, 3],
                            tags=[
                                Tag(
                                    time_seconds=0.5,
                                    action=True,
                                    colors=[[1, 2, 3]],
                                )
                            ],
                        ),
                    },
                ),
                "s2": Slave(
                    id="s2",
                    name="Back",
                    pin="8",
                    led_count=60,
                    tag_types={},
                ),
            },
        )
        m_out = unpack_master(pack_master(m_in))
        self.assertEqual(m_out, m_in)


if __name__ == "__main__":
    unittest.main()
