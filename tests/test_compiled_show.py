import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.compiled_show import (
    HEADER_STRUCT,
    MAGIC,
    OP_SOLID,
    SEGMENT_STRUCT,
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
            id="s1",
            name="slave",
            pin="7",
            led_count=16,
            grid_rows=1,
            grid_columns=16,
            led_cells=list(range(16)),
            tag_types={"front": tag_type},
        )
        master = Master(id="m1", name="master", ip="192.168.0.50", slaves={"s1": slave})

        compiled = CompileShowsForMastersUseCase().execute({"m1": master})
        show = compiled["192.168.0.50"][0]

        self.assertEqual(7, show.slave_id)
        self.assertTrue(show.blob.startswith(MAGIC))
        self.assertGreater(len(show.blob), 16)

    def test_compiled_show_uses_led_cells_for_wire_order(self):
        """With led_cells=[3,2,1,0] (wire-reversed), canvas cell 3
        lives at wire position 0. A single-cell topology targeting
        cell 3 must produce a valid blob whose payload references
        that cell's blue color at wire position 0 of the segment.
        """
        tag_type = TagType(
            name="one",
            pin="0",
            rows=1,
            columns=1,
            topology=[3],
            tags=[Tag(time_seconds=0.0, action="On", colors=[[0, 0, 255]])],
        )
        slave = Slave(
            id="s1",
            name="slave",
            pin="1",
            led_count=4,
            grid_rows=2,
            grid_columns=2,
            led_cells=[3, 2, 1, 0],
            tag_types={"one": tag_type},
        )
        master = Master(id="m1", name="master", ip="192.168.0.10", slaves={"s1": slave})

        compiled = CompileShowsForMastersUseCase().execute({"m1": master})
        show = compiled["192.168.0.10"][0]
        blob = show.blob

        magic, version, slave_id, total, n_segs, n_palette, n_events = (
            HEADER_STRUCT.unpack(blob[: HEADER_STRUCT.size])
        )
        self.assertEqual(MAGIC, magic)
        self.assertEqual(1, version)
        self.assertEqual(1, slave_id)
        self.assertEqual(1, n_segs)
        self.assertEqual(1, n_events)
        # Palette includes black (index 0) + blue.
        self.assertEqual(2, n_palette)

        seg_start = HEADER_STRUCT.size
        seg_data = blob[seg_start : seg_start + SEGMENT_STRUCT.size]
        start, size = SEGMENT_STRUCT.unpack(seg_data)
        self.assertEqual(1, size)

        palette_start = seg_start + SEGMENT_STRUCT.size
        palette_bytes = blob[palette_start : palette_start + 3 * n_palette]
        # Black occupies palette index 0.
        self.assertEqual((0, 0, 0), tuple(palette_bytes[0:3]))
        # Blue should be added as index 1.
        self.assertEqual((0, 0, 255), tuple(palette_bytes[3:6]))

        events_start = palette_start + 3 * n_palette
        # First event: varuint dt=0 (single byte 0x00), then opcode,
        # then segment_id, then payload (OP_SOLID: single color id).
        self.assertEqual(0x00, blob[events_start])
        self.assertEqual(OP_SOLID, blob[events_start + 1])
        self.assertEqual(0, blob[events_start + 2])
        self.assertEqual(1, blob[events_start + 3])  # color id = blue

    def test_compiled_show_migrated_layout_unchanged(self):
        """For migrated projects where led_cells=[0..N-1], the
        compiled blob must be byte-identical to what pre-8.7
        produced (i.e. equivalent to the build that did no
        led_cells filtering)."""
        tag_type = TagType(
            name="front",
            pin="0",
            rows=1,
            columns=4,
            topology=[0, 1, 2, 3],
            tags=[
                Tag(time_seconds=0.0, action="On", colors=[[255, 0, 0]] * 4),
                Tag(time_seconds=0.5, action="Off", colors=[[0, 0, 0]] * 4),
            ],
        )
        with_cells = Slave(
            id="s1",
            name="slave",
            pin="2",
            led_count=4,
            grid_rows=1,
            grid_columns=4,
            led_cells=[0, 1, 2, 3],
            tag_types={"front": tag_type},
        )
        # Simulate a pre-v3 slave (no led_cells) by constructing a
        # slave with led_cells=[]; kept-indices filter is bypassed
        # when led_cells is empty, reproducing pre-8.7 behavior.
        no_cells = Slave(
            id="s1",
            name="slave",
            pin="2",
            led_count=4,
            grid_rows=1,
            grid_columns=4,
            led_cells=[],
            tag_types={"front": tag_type},
        )
        m_cells = Master(
            id="m1", name="master", ip="192.168.0.50", slaves={"s1": with_cells}
        )
        m_nocells = Master(
            id="m1", name="master", ip="192.168.0.50", slaves={"s1": no_cells}
        )

        compiled_cells = CompileShowsForMastersUseCase().execute({"m1": m_cells})
        compiled_nocells = CompileShowsForMastersUseCase().execute({"m1": m_nocells})
        blob_cells = compiled_cells["192.168.0.50"][0].blob
        blob_nocells = compiled_nocells["192.168.0.50"][0].blob
        self.assertEqual(blob_nocells, blob_cells)

        # Additionally, assert the blob layout bytes match a manually
        # constructed expected prefix: MAGIC + version + slave_id +
        # total_led_count + n_segments=1 + n_palette=2 (black, red) +
        # n_events=2.
        header = HEADER_STRUCT.unpack(blob_cells[: HEADER_STRUCT.size])
        magic, version, slave_id, total, n_segs, n_palette, n_events = header
        self.assertEqual(MAGIC, magic)
        self.assertEqual(1, version)
        self.assertEqual(2, slave_id)
        self.assertEqual(4, total)
        self.assertEqual(1, n_segs)
        self.assertEqual(2, n_palette)
        self.assertEqual(2, n_events)

        seg_start = HEADER_STRUCT.size
        start, size = SEGMENT_STRUCT.unpack(
            blob_cells[seg_start : seg_start + SEGMENT_STRUCT.size]
        )
        self.assertEqual(0, start)
        self.assertEqual(4, size)

        palette_start = seg_start + SEGMENT_STRUCT.size
        self.assertEqual(
            bytes([0, 0, 0, 255, 0, 0]),
            blob_cells[palette_start : palette_start + 6],
        )


if __name__ == "__main__":
    unittest.main()
