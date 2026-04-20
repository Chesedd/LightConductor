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
    render_canvas_with_overlay,
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


class LedPreviewOverlayTests(unittest.TestCase):
    def test_overlay_type_missing_returns_base(self):
        tt = make_tt(
            "alpha",
            "1",
            [0, 1],
            tags=[
                Tag(
                    time_seconds=0.0,
                    action=True,
                    colors=[[255, 0, 0], [255, 0, 0]],
                )
            ],
        )
        slave = make_slave(3, {"alpha": tt})
        result = render_canvas_with_overlay(
            slave,
            0.0,
            "beta",
            [[0, 255, 0]],
            True,
        )
        self.assertEqual(
            [(255, 0, 0), (255, 0, 0), (0, 0, 0)],
            result,
        )
        self.assertIs(type(result[0]), tuple)

    def test_empty_slave_returns_empty_with_overlay(self):
        slave = make_slave(0)
        self.assertEqual(
            [],
            render_canvas_with_overlay(
                slave,
                0.0,
                "alpha",
                [[255, 0, 0]],
                True,
            ),
        )

    def test_overlay_replaces_existing_tag_of_same_type(self):
        tt = make_tt(
            "alpha",
            "1",
            [0, 1, 2],
            tags=[
                Tag(
                    time_seconds=0.0,
                    action=True,
                    colors=[[255, 0, 0], [255, 0, 0], [255, 0, 0]],
                )
            ],
        )
        slave = make_slave(3, {"alpha": tt})
        result = render_canvas_with_overlay(
            slave,
            0.0,
            "alpha",
            [[0, 255, 0], [0, 255, 0], [0, 255, 0]],
            True,
        )
        self.assertEqual(
            [(0, 255, 0), (0, 255, 0), (0, 255, 0)],
            result,
        )
        self.assertIs(type(result[0]), tuple)

    def test_overlay_action_false_clears_its_segment(self):
        tt = make_tt(
            "alpha",
            "1",
            [0, 1],
            tags=[
                Tag(
                    time_seconds=0.0,
                    action=True,
                    colors=[[255, 0, 0], [255, 0, 0]],
                )
            ],
        )
        slave = make_slave(3, {"alpha": tt})
        result = render_canvas_with_overlay(
            slave,
            0.0,
            "alpha",
            [[255, 0, 0], [255, 0, 0]],
            False,
        )
        self.assertEqual(
            [(0, 0, 0), (0, 0, 0), (0, 0, 0)],
            result,
        )

    def test_overlay_coexists_with_other_type(self):
        tt_alpha = make_tt("alpha", "1", [0], tags=[])
        tt_beta = make_tt(
            "beta",
            "2",
            [1],
            tags=[
                Tag(
                    time_seconds=0.0,
                    action=True,
                    colors=[[0, 0, 255]],
                )
            ],
        )
        slave = make_slave(2, {"alpha": tt_alpha, "beta": tt_beta})
        result = render_canvas_with_overlay(
            slave,
            0.0,
            "alpha",
            [[255, 0, 0]],
            True,
        )
        self.assertEqual([(255, 0, 0), (0, 0, 255)], result)
        self.assertIs(type(result[0]), tuple)
        self.assertIs(type(result[1]), tuple)

    def test_overlay_colors_shorter_pad_black(self):
        tt = make_tt("alpha", "1", [0, 1, 2], tags=[])
        slave = make_slave(3, {"alpha": tt})
        result = render_canvas_with_overlay(
            slave,
            0.0,
            "alpha",
            [[255, 0, 0]],
            True,
        )
        self.assertEqual(
            [(255, 0, 0), (0, 0, 0), (0, 0, 0)],
            result,
        )

    def test_overlay_colors_longer_truncated(self):
        tt = make_tt("alpha", "1", [0], tags=[])
        slave = make_slave(1, {"alpha": tt})
        result = render_canvas_with_overlay(
            slave,
            0.0,
            "alpha",
            [[255, 0, 0], [0, 255, 0]],
            True,
        )
        self.assertEqual([(255, 0, 0)], result)

    def test_overlay_topology_oor_skipped(self):
        tt = make_tt("alpha", "1", [0, 5, 2], tags=[])
        slave = make_slave(3, {"alpha": tt})
        result = render_canvas_with_overlay(
            slave,
            0.0,
            "alpha",
            [[255, 0, 0], [255, 0, 0], [255, 0, 0]],
            True,
        )
        self.assertEqual(
            [(255, 0, 0), (0, 0, 0), (255, 0, 0)],
            result,
        )

    def test_overlay_on_nonexistent_time_base_is_off(self):
        tt = make_tt(
            "alpha",
            "1",
            [0],
            tags=[
                Tag(
                    time_seconds=5.0,
                    action=True,
                    colors=[[255, 0, 0]],
                )
            ],
        )
        slave = make_slave(1, {"alpha": tt})
        result = render_canvas_with_overlay(
            slave,
            0.0,
            "alpha",
            [[0, 255, 0]],
            True,
        )
        self.assertEqual([(0, 255, 0)], result)

    def test_overlay_string_action_on(self):
        tt = make_tt("alpha", "1", [0], tags=[])
        slave = make_slave(1, {"alpha": tt})
        on_result = render_canvas_with_overlay(
            slave,
            0.0,
            "alpha",
            [[255, 0, 0]],
            "On",
        )
        self.assertEqual([(255, 0, 0)], on_result)
        self.assertIs(type(on_result[0]), tuple)

        off_result = render_canvas_with_overlay(
            slave,
            0.0,
            "alpha",
            [[255, 0, 0]],
            "Off",
        )
        self.assertEqual([(0, 0, 0)], off_result)

    def test_overlay_on_2d_canvas(self):
        tt = make_tt("alpha", "1", [0, 3], tags=[])
        slave = make_slave(
            6,
            {"alpha": tt},
            grid_rows=2,
            grid_columns=3,
            led_cells=[0, 1, 2, 3, 4, 5],
        )
        result = render_canvas_with_overlay(
            slave,
            0.0,
            "alpha",
            [[0, 255, 0], [0, 255, 0]],
            True,
        )
        self.assertEqual(6, len(result))
        self.assertEqual((0, 255, 0), result[0])
        self.assertEqual((0, 255, 0), result[3])
        for idx in (1, 2, 4, 5):
            self.assertEqual((0, 0, 0), result[idx])


if __name__ == "__main__":
    unittest.main()
