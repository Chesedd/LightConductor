import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.led_preview import (
    cell_to_wire_index,
    render_canvas_at,
)
from lightconductor.domain.models import Slave, Tag, TagType


def make_slave(
    led_count,
    tag_types=None,
    grid_rows=1,
    grid_columns=None,
    led_cells=None,
):
    cols = grid_columns if grid_columns is not None else led_count
    cells = list(led_cells) if led_cells is not None else list(range(max(0, led_count)))
    return Slave(
        id="s",
        name="s",
        pin="1",
        led_count=led_count,
        grid_rows=grid_rows,
        grid_columns=cols,
        led_cells=cells,
        tag_types=tag_types or {},
    )


def make_tt(name, pin, topology, tags=None):
    return TagType(
        name=name,
        pin=pin,
        rows=1,
        columns=len(topology),
        topology=topology,
        tags=tags or [],
    )


class LedPreviewTests(unittest.TestCase):
    def test_empty_slave_returns_empty_buffer(self):
        slave = make_slave(0)
        self.assertEqual([], render_canvas_at(slave, 0.0))

    def test_canvas_zero_returns_empty_buffer(self):
        slave = Slave(
            id="s",
            name="s",
            pin="1",
            led_count=5,
            grid_rows=0,
            grid_columns=0,
        )
        self.assertEqual([], render_canvas_at(slave, 0.0))

    def test_no_tag_types_returns_all_off(self):
        slave = make_slave(5, {})
        self.assertEqual([(0, 0, 0)] * 5, render_canvas_at(slave, 0.0))

    def test_tag_before_first_time_is_off(self):
        tt = make_tt(
            "a",
            "1",
            [0, 1, 2],
            tags=[Tag(time_seconds=1.0, action=True, colors=[[255, 0, 0]] * 3)],
        )
        slave = make_slave(3, {"a": tt})
        self.assertEqual([(0, 0, 0)] * 3, render_canvas_at(slave, 0.5))

    def test_tag_at_exact_time_active(self):
        tt = make_tt(
            "a",
            "1",
            [0, 1, 2],
            tags=[Tag(time_seconds=1.0, action=True, colors=[[255, 0, 0]] * 3)],
        )
        slave = make_slave(3, {"a": tt})
        result = render_canvas_at(slave, 1.0)
        self.assertEqual([(255, 0, 0), (255, 0, 0), (255, 0, 0)], result)

    def test_action_false_clears_segment(self):
        tt = make_tt(
            "a",
            "1",
            [0, 1, 2],
            tags=[
                Tag(time_seconds=0.0, action=True, colors=[[255, 0, 0]] * 3),
                Tag(time_seconds=1.0, action=False, colors=[[0, 0, 0]] * 3),
            ],
        )
        slave = make_slave(3, {"a": tt})
        self.assertEqual([(0, 0, 0)] * 3, render_canvas_at(slave, 1.5))

    def test_latest_tag_wins(self):
        tt = make_tt(
            "a",
            "1",
            [0, 1, 2],
            tags=[
                Tag(time_seconds=0.0, action=True, colors=[[255, 0, 0]] * 3),
                Tag(time_seconds=1.0, action=True, colors=[[0, 255, 0]] * 3),
                Tag(time_seconds=2.0, action=True, colors=[[0, 0, 255]] * 3),
            ],
        )
        slave = make_slave(3, {"a": tt})
        result = render_canvas_at(slave, 1.5)
        self.assertEqual([(0, 255, 0), (0, 255, 0), (0, 255, 0)], result)

    def test_topology_out_of_range_skipped(self):
        tt = make_tt(
            "a",
            "1",
            [0, 5, 2],
            tags=[Tag(time_seconds=0.0, action=True, colors=[[255, 0, 0]] * 3)],
        )
        slave = make_slave(3, {"a": tt})
        result = render_canvas_at(slave, 0.0)
        self.assertEqual([(255, 0, 0), (0, 0, 0), (255, 0, 0)], result)

    def test_colors_shorter_than_topology_pads_black(self):
        tt = make_tt(
            "a",
            "1",
            [0, 1, 2],
            tags=[Tag(time_seconds=0.0, action=True, colors=[[255, 0, 0]])],
        )
        slave = make_slave(3, {"a": tt})
        result = render_canvas_at(slave, 0.0)
        self.assertEqual([(255, 0, 0), (0, 0, 0), (0, 0, 0)], result)

    def test_colors_longer_than_topology_truncated(self):
        tt = make_tt(
            "a",
            "1",
            [0],
            tags=[
                Tag(time_seconds=0.0, action=True, colors=[[255, 0, 0], [0, 255, 0]])
            ],
        )
        slave = make_slave(1, {"a": tt})
        result = render_canvas_at(slave, 0.0)
        self.assertEqual([(255, 0, 0)], result)

    def test_string_action_on(self):
        tt = make_tt(
            "a",
            "1",
            [0, 1, 2],
            tags=[Tag(time_seconds=0.0, action="On", colors=[[10, 20, 30]] * 3)],
        )
        slave = make_slave(3, {"a": tt})
        result = render_canvas_at(slave, 0.0)
        self.assertEqual([(10, 20, 30), (10, 20, 30), (10, 20, 30)], result)

    def test_string_action_off(self):
        tt = make_tt(
            "a",
            "1",
            [0, 1, 2],
            tags=[Tag(time_seconds=0.0, action="Off", colors=[[10, 20, 30]] * 3)],
        )
        slave = make_slave(3, {"a": tt})
        result = render_canvas_at(slave, 0.0)
        self.assertEqual([(0, 0, 0)] * 3, result)

    def test_overlapping_topology_last_pin_wins(self):
        tt_red = make_tt(
            "red",
            "1",
            [0],
            tags=[Tag(time_seconds=0.0, action=True, colors=[[255, 0, 0]])],
        )
        tt_blue = make_tt(
            "blue",
            "2",
            [0],
            tags=[Tag(time_seconds=0.0, action=True, colors=[[0, 0, 255]])],
        )
        slave_a = make_slave(1, {"red": tt_red, "blue": tt_blue})
        slave_b = make_slave(1, {"blue": tt_blue, "red": tt_red})
        self.assertEqual([(0, 0, 255)], render_canvas_at(slave_a, 0.0))
        self.assertEqual([(0, 0, 255)], render_canvas_at(slave_b, 0.0))

    def test_color_string_format(self):
        tt = make_tt(
            "a",
            "1",
            [0],
            tags=[Tag(time_seconds=0.0, action=True, colors=["255,0,128"])],
        )
        slave = make_slave(1, {"a": tt})
        result = render_canvas_at(slave, 0.0)
        self.assertEqual([(255, 0, 128)], result)

    def test_color_out_of_range_clamped(self):
        tt = make_tt(
            "a",
            "1",
            [0],
            tags=[Tag(time_seconds=0.0, action=True, colors=[[300, -5, 128]])],
        )
        slave = make_slave(1, {"a": tt})
        result = render_canvas_at(slave, 0.0)
        self.assertEqual([(255, 0, 128)], result)
        self.assertIs(type(result[0]), tuple)

    def test_render_canvas_respects_grid_columns_for_2d_slave(self):
        tt = make_tt(
            "a",
            "1",
            [0, 3],
            tags=[
                Tag(
                    time_seconds=0.0,
                    action=True,
                    colors=[[255, 0, 0], [255, 0, 0]],
                )
            ],
        )
        slave = make_slave(
            6,
            {"a": tt},
            grid_rows=2,
            grid_columns=3,
            led_cells=[0, 1, 2, 3, 4, 5],
        )
        result = render_canvas_at(slave, 0.0)
        self.assertEqual(6, len(result))
        self.assertEqual((255, 0, 0), result[0])
        self.assertEqual((255, 0, 0), result[3])
        for idx in (1, 2, 4, 5):
            self.assertEqual((0, 0, 0), result[idx])

    def test_render_canvas_with_larger_canvas_than_leds(self):
        tt = make_tt(
            "a",
            "1",
            [0, 4],
            tags=[
                Tag(
                    time_seconds=0.0,
                    action=True,
                    colors=[[0, 255, 0], [0, 255, 0]],
                )
            ],
        )
        slave = make_slave(
            4,
            {"a": tt},
            grid_rows=3,
            grid_columns=3,
            led_cells=[0, 1, 4, 8],
        )
        result = render_canvas_at(slave, 0.0)
        self.assertEqual(9, len(result))
        self.assertEqual((0, 255, 0), result[0])
        self.assertEqual((0, 255, 0), result[4])
        for idx in (1, 2, 3, 5, 6, 7, 8):
            self.assertEqual((0, 0, 0), result[idx])


class CellToWireIndexTests(unittest.TestCase):
    def test_cell_to_wire_index_for_custom_order(self):
        slave = Slave(
            id="s",
            name="s",
            pin="1",
            led_count=4,
            grid_rows=2,
            grid_columns=2,
            led_cells=[3, 1, 0, 2],
        )
        self.assertEqual(2, cell_to_wire_index(slave, 0))
        self.assertEqual(1, cell_to_wire_index(slave, 1))
        self.assertEqual(3, cell_to_wire_index(slave, 2))
        self.assertEqual(0, cell_to_wire_index(slave, 3))

    def test_cell_to_wire_index_returns_none_for_non_led_cell(self):
        slave = Slave(
            id="s",
            name="s",
            pin="1",
            led_count=2,
            grid_rows=1,
            grid_columns=3,
            led_cells=[0, 1],
        )
        self.assertIsNone(cell_to_wire_index(slave, 2))


if __name__ == "__main__":
    unittest.main()
