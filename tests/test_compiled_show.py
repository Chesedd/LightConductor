import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.compiled_show import (
    MAGIC,
    CompileShowsForMastersUseCase,
)
from lightconductor.domain.models import Master, Slave, Tag, TagType


class CompiledShowTests(unittest.TestCase):
    def test_compiles_single_slave_blob(self):
        tag_type = TagType(
            name="front",
            pin="3",
            rows=1,
            columns=4,
            topology=[0, 1, 2, 3],
            tags=[
                Tag(time_seconds=0.10, action="On", colors=[[255, 0, 0]] * 4),
                Tag(time_seconds=0.35, action="Off", colors=[[0, 0, 0]] * 4),
            ],
        )
        slave = Slave(
            id="s1", name="slave", pin="7", led_count=16, tag_types={"front": tag_type}
        )
        master = Master(id="m1", name="master", ip="192.168.0.50", slaves={"s1": slave})

        compiled = CompileShowsForMastersUseCase().execute({"m1": master})
        show = compiled["192.168.0.50"][0]

        self.assertEqual(7, show.slave_id)
        self.assertTrue(show.blob.startswith(MAGIC))
        self.assertGreater(len(show.blob), 16)


if __name__ == "__main__":
    unittest.main()
