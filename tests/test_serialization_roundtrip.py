import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ProjectScreen.ProjectManager import ProjectManager


class FakeTag:
    def __init__(self, time, action, colors):
        self.time = time
        self.action = action
        self.colors = colors


class FakeType:
    def __init__(self, name, color, pin, row, table, topology, tags):
        self.name = name
        self.color = color
        self.pin = pin
        self.row = row
        self.table = table
        self.topology = list(topology)
        self.tags = list(tags)


class FakeManager:
    def __init__(self, types):
        self.types = dict(types)


class FakeWave:
    def __init__(self, manager):
        self.manager = manager


class FakeSlave:
    def __init__(self, title, boxID, slavePin, ledCount, types):
        self.title = title
        self.boxID = boxID
        self.slavePin = slavePin
        self.ledCount = ledCount
        self.wave = FakeWave(FakeManager(types))


class FakeMaster:
    def __init__(self, title, boxID, masterIp, slaves):
        self.title = title
        self.boxID = boxID
        self.masterIp = masterIp
        self.slaves = dict(slaves)


def _pack_project(masters):
    """masters: dict[master_id, FakeMaster] -> dict[master_id, dict]."""
    pm = ProjectManager.__new__(ProjectManager)
    boxes = {}
    for master_id, master in masters.items():
        slaves_data = {}
        for slave_id, slave in master.slaves.items():
            types_data = {}
            for type_name, t in slave.wave.manager.types.items():
                tags_data = {}
                for i, tag in enumerate(t.tags):
                    tags_data[i] = pm.packTag(tag)
                types_data[type_name] = pm.packType(t, tags_data)
            slaves_data[slave_id] = pm.packSlave(slave, types_data)
        boxes[master_id] = pm.packMaster(master, slaves_data)
    return boxes


def _unpack_project(boxes):
    """boxes: dict[master_id, master_dict] -> dict[master_id, FakeMaster].

    Note: segment_start/segment_size are intentionally ignored — they are
    fully derived from pin/topology by packType. This is what makes the
    double-pack comparison correct.
    """
    masters = {}
    for master_id, m in boxes.items():
        slaves = {}
        for slave_id, s in m["slaves"].items():
            types = {}
            for type_name, t in s["tagTypes"].items():
                tags = []
                for _, tag_data in t["tags"].items():
                    tags.append(FakeTag(
                        time=tag_data["time"],
                        action=tag_data["action"],
                        colors=tag_data["colors"],
                    ))
                types[type_name] = FakeType(
                    name=type_name,
                    color=t["color"],
                    pin=t["pin"],
                    row=t["row"],
                    table=t["table"],
                    topology=list(t["topology"]),
                    tags=tags,
                )
            slaves[slave_id] = FakeSlave(
                title=s["name"],
                boxID=s["id"],
                slavePin=s["pin"],
                ledCount=s["led_count"],
                types=types,
            )
        masters[master_id] = FakeMaster(
            title=m["name"],
            boxID=m["id"],
            masterIp=m.get("ip", "192.168.0.129"),
            slaves=slaves,
        )
    return masters


def _round_trip(masters):
    packed_once = _pack_project(masters)
    unpacked = _unpack_project(packed_once)
    packed_twice = _pack_project(unpacked)
    return packed_once, packed_twice


def _make_tag(time=0.0, action="on", colors=None):
    if colors is None:
        colors = [[255, 255, 255]]
    return FakeTag(time=time, action=action, colors=colors)


def _make_type(name="red", color="#FF0000", pin=0, row=0, table=0,
               topology=(0,), tags=()):
    return FakeType(
        name=name,
        color=color,
        pin=pin,
        row=row,
        table=table,
        topology=list(topology),
        tags=list(tags),
    )


def _make_slave(title="slave-1", boxID="s1", slavePin=1, ledCount=60,
                types=None):
    return FakeSlave(
        title=title,
        boxID=boxID,
        slavePin=slavePin,
        ledCount=ledCount,
        types=types or {},
    )


def _make_master(title="master-1", boxID="m1", masterIp="192.168.0.129",
                 slaves=None):
    return FakeMaster(
        title=title,
        boxID=boxID,
        masterIp=masterIp,
        slaves=slaves or {},
    )


class SerializationRoundTripTests(unittest.TestCase):

    def test_empty_project_roundtrip(self):
        packed_once, packed_twice = _round_trip({})
        self.assertEqual(packed_once, {})
        self.assertEqual(packed_once, packed_twice)

    def test_master_without_slaves(self):
        masters = {"m1": _make_master()}
        packed_once, packed_twice = _round_trip(masters)
        self.assertEqual(packed_once, packed_twice)
        self.assertEqual(packed_once["m1"]["slaves"], {})

    def test_slave_without_tag_types(self):
        slave = _make_slave()
        master = _make_master(slaves={"s1": slave})
        packed_once, packed_twice = _round_trip({"m1": master})
        self.assertEqual(packed_once, packed_twice)
        self.assertEqual(packed_once["m1"]["slaves"]["s1"]["tagTypes"], {})

    def test_type_without_tags(self):
        t = _make_type(tags=[])
        slave = _make_slave(types={"red": t})
        master = _make_master(slaves={"s1": slave})
        packed_once, packed_twice = _round_trip({"m1": master})
        self.assertEqual(packed_once, packed_twice)
        self.assertEqual(
            packed_once["m1"]["slaves"]["s1"]["tagTypes"]["red"]["tags"],
            {},
        )

    def test_minimal_full_project(self):
        tag = _make_tag(time=1.5, action="fade", colors=[[10, 20, 30]])
        t = _make_type(tags=[tag])
        slave = _make_slave(types={"red": t})
        master = _make_master(slaves={"s1": slave})
        packed_once, packed_twice = _round_trip({"m1": master})
        self.assertEqual(packed_once, packed_twice)
        tag_d = packed_once["m1"]["slaves"]["s1"]["tagTypes"]["red"]["tags"][0]
        self.assertEqual(tag_d["time"], 1.5)
        self.assertEqual(tag_d["action"], "fade")
        self.assertEqual(tag_d["colors"], [[10, 20, 30]])

    def test_multi_level_project(self):
        tag_a = _make_tag(time=0.1, action="on", colors=[[255, 0, 0]])
        tag_b = _make_tag(time=0.2, action="off", colors=[[0, 255, 0]])
        tag_c = _make_tag(time=0.3, action="fade", colors=[[0, 0, 255]])

        type_red = _make_type(
            name="red", color="#FF0000", pin=1, row=0, table=0,
            topology=[0, 1], tags=[tag_a, tag_b],
        )
        type_blue = _make_type(
            name="blue", color="#0000FF", pin=2, row=1, table=0,
            topology=[2, 3, 4], tags=[tag_c],
        )
        type_green = _make_type(
            name="green", color="#00FF00", pin=3, row=0, table=1,
            topology=[5], tags=[],
        )

        slave1 = _make_slave(
            title="s1-title", boxID="s1", slavePin=1, ledCount=60,
            types={"red": type_red, "blue": type_blue},
        )
        slave2 = _make_slave(
            title="s2-title", boxID="s2", slavePin=2, ledCount=120,
            types={"green": type_green},
        )
        slave3 = _make_slave(
            title="s3-title", boxID="s3", slavePin=3, ledCount=30,
            types={},
        )

        master1 = _make_master(
            title="master-A", boxID="m1", masterIp="192.168.0.10",
            slaves={"s1": slave1, "s2": slave2},
        )
        master2 = _make_master(
            title="master-B", boxID="m2", masterIp="192.168.0.20",
            slaves={"s3": slave3},
        )

        packed_once, packed_twice = _round_trip({"m1": master1, "m2": master2})
        self.assertEqual(packed_once, packed_twice)
        self.assertEqual(packed_once["m1"]["ip"], "192.168.0.10")
        self.assertEqual(packed_once["m2"]["ip"], "192.168.0.20")
        self.assertEqual(
            packed_once["m1"]["slaves"]["s1"]["tagTypes"]["red"]["tags"][1]["action"],
            "off",
        )
        self.assertEqual(
            len(packed_once["m1"]["slaves"]["s1"]["tagTypes"]["blue"]["tags"]),
            1,
        )

    def test_unicode_in_names(self):
        tag = _make_tag(colors=[[1, 2, 3]])
        t = _make_type(name="красный", tags=[tag])
        slave = _make_slave(title="一号", types={"красный": t})
        master = _make_master(title="Мастер 🎨", slaves={"s1": slave})
        packed_once, packed_twice = _round_trip({"m1": master})
        self.assertEqual(packed_once, packed_twice)
        self.assertEqual(packed_once["m1"]["name"], "Мастер 🎨")
        self.assertEqual(packed_once["m1"]["slaves"]["s1"]["name"], "一号")
        self.assertIn(
            "красный",
            packed_once["m1"]["slaves"]["s1"]["tagTypes"],
        )

    def test_numeric_pin_preserved(self):
        # int pin
        t_int = _make_type(pin=3, topology=[0, 1, 2])
        slave_int = _make_slave(types={"red": t_int})
        master_int = _make_master(slaves={"s1": slave_int})
        packed_once, packed_twice = _round_trip({"m1": master_int})
        self.assertEqual(packed_once, packed_twice)
        pin_once = packed_once["m1"]["slaves"]["s1"]["tagTypes"]["red"]["pin"]
        self.assertEqual(pin_once, 3)
        self.assertIsInstance(pin_once, int)

        # str pin
        t_str = _make_type(pin="3", topology=[0, 1, 2])
        slave_str = _make_slave(types={"red": t_str})
        master_str = _make_master(slaves={"s1": slave_str})
        packed_once, packed_twice = _round_trip({"m1": master_str})
        self.assertEqual(packed_once, packed_twice)
        pin_once = packed_once["m1"]["slaves"]["s1"]["tagTypes"]["red"]["pin"]
        self.assertEqual(pin_once, "3")
        self.assertIsInstance(pin_once, str)

    def test_topology_order_preserved(self):
        t = _make_type(topology=[3, 1, 0, 2])
        slave = _make_slave(types={"red": t})
        master = _make_master(slaves={"s1": slave})
        packed_once, packed_twice = _round_trip({"m1": master})
        self.assertEqual(packed_once, packed_twice)
        self.assertEqual(
            packed_once["m1"]["slaves"]["s1"]["tagTypes"]["red"]["topology"],
            [3, 1, 0, 2],
        )

    def test_multiple_colors_per_tag(self):
        tag = _make_tag(colors=[[255, 0, 0], [0, 255, 0], [0, 0, 255]])
        t = _make_type(tags=[tag])
        slave = _make_slave(types={"red": t})
        master = _make_master(slaves={"s1": slave})
        packed_once, packed_twice = _round_trip({"m1": master})
        self.assertEqual(packed_once, packed_twice)
        self.assertEqual(
            packed_once["m1"]["slaves"]["s1"]["tagTypes"]["red"]["tags"][0]["colors"],
            [[255, 0, 0], [0, 255, 0], [0, 0, 255]],
        )

    def test_master_without_masterIp_attribute(self):
        master = object.__new__(FakeMaster)
        master.title = "no-ip-master"
        master.boxID = "m1"
        master.slaves = {}
        self.assertFalse(hasattr(master, "masterIp"))

        packed_once, packed_twice = _round_trip({"m1": master})
        self.assertEqual(packed_once, packed_twice)
        self.assertEqual(packed_once["m1"]["ip"], "192.168.0.129")

        # Unpack should produce a FakeMaster with masterIp set to the fallback.
        unpacked = _unpack_project(packed_once)
        self.assertEqual(unpacked["m1"].masterIp, "192.168.0.129")
        repacked = _pack_project(unpacked)
        self.assertEqual(repacked["m1"]["ip"], "192.168.0.129")

    def test_pack_type_segment_start_mirrors_pin(self):
        pm = ProjectManager.__new__(ProjectManager)
        t = _make_type(pin="7", topology=[0, 1, 2, 3])
        d = pm.packType(t, {})
        self.assertEqual(d["segment_start"], d["pin"])
        self.assertEqual(d["segment_start"], "7")

    def test_pack_type_segment_size_equals_topology_length(self):
        pm = ProjectManager.__new__(ProjectManager)
        t = _make_type(topology=[0, 1, 2, 3, 4])
        d = pm.packType(t, {})
        self.assertEqual(d["segment_size"], 5)


if __name__ == "__main__":
    unittest.main()
