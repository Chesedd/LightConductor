import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application import BuildShowPayloadUseCase
from lightconductor.domain.models import Master, Slave, Tag, TagType


class PayloadPipelineTests(unittest.TestCase):
    def test_payload_pipeline_on_domain_masters(self):
        use_case = BuildShowPayloadUseCase()
        tt = TagType(
            name="front", pin="3", rows=2, columns=2,
            color=[255, 255, 255], topology=[0, 1, 2, 3],
            tags=[
                Tag(time_seconds=0.1, action=True, colors=[[255, 0, 0]]),
                Tag(time_seconds=0.25, action=False, colors=[[0, 0, 0]]),
            ],
        )
        slave = Slave(
            id="slave-1", name="Slave A", pin="7", led_count=4,
            tag_types={"front": tt},
        )
        master = Master(
            id="master-1", name="Master A", ip="192.168.0.1",
            slaves={"slave-1": slave},
        )
        masters = {"master-1": master}
        pins, payload = use_case.execute(masters)

        self.assertEqual({"7": {"front": 4}}, pins)
        self.assertIn(100, payload["7"])
        self.assertIn(250, payload["7"])
        self.assertEqual(True, payload["7"][100]["front"]["action"])
        self.assertEqual(False, payload["7"][250]["front"]["action"])
        self.assertEqual(3, payload["7"][100]["front"]["segment_start"])
        self.assertEqual(4, payload["7"][100]["front"]["segment_size"])


if __name__ == "__main__":
    unittest.main()
