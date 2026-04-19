import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application import BuildShowPayloadUseCase
from lightconductor.infrastructure import UiMastersMapper


class FakeTag:
    def __init__(self, time, action, colors):
        self.time = time
        self.action = action
        self.colors = colors


class FakeType:
    def __init__(self, pin, row, table, color, tags):
        self.pin = pin
        self.row = row
        self.table = table
        self.color = color
        self.tags = tags


class FakeManager:
    def __init__(self, types):
        self.types = types


class FakeWave:
    def __init__(self, manager):
        self.manager = manager


class FakeSlave:
    def __init__(self, title, slave_pin, wave):
        self.title = title
        self.slavePin = slave_pin
        self.wave = wave


class FakeMaster:
    def __init__(self, title, slaves):
        self.title = title
        self.slaves = slaves


class PayloadPipelineTests(unittest.TestCase):
    def test_map_and_build_payload(self):
        mapper = UiMastersMapper()
        use_case = BuildShowPayloadUseCase()

        tags = [
            FakeTag(0.1, True, [[255, 0, 0]]),
            FakeTag(0.25, False, [[0, 0, 0]]),
        ]
        types = {"front": FakeType(pin="3", row=2, table=2, color=[255, 255, 255], tags=tags)}
        manager = FakeManager(types=types)
        wave = FakeWave(manager=manager)
        slave = FakeSlave(title="Slave A", slave_pin="7", wave=wave)
        master = FakeMaster(title="Master A", slaves={"slave-1": slave})

        mapped = mapper.map_masters({"master-1": master})
        pins, payload = use_case.execute(mapped)

        self.assertEqual({"7": {"front": 4}}, pins)
        self.assertIn(100, payload["7"])
        self.assertIn(250, payload["7"])
        self.assertEqual(True, payload["7"][100]["front"]["action"])
        self.assertEqual(False, payload["7"][250]["front"]["action"])
        self.assertEqual(3, payload["7"][100]["front"]["segment_start"])
        self.assertEqual(4, payload["7"][100]["front"]["segment_size"])


if __name__ == "__main__":
    unittest.main()
