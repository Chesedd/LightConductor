"""Programmatic drag-paint tests for TopologyDialog, LedWireDialog
and TagPinsDialog.

Qt mouse events cannot be synthesized reliably in a headless CI
environment, so these tests drive the dialog's drag state machine
directly via the `_drag_begin` / `_drag_apply` / `_drag_end` hooks.
Visual routing (eventFilter + widgetAt) is left for local
verification.
"""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from ProjectScreen.PlateLogic.LedWireDialog import LedWireDialog  # noqa: E402
from ProjectScreen.PlateLogic.TagPinsDialog import TagPinsDialog  # noqa: E402
from ProjectScreen.TagLogic.TagManager import TopologyDialog  # noqa: E402

_app: QApplication | None = None


def _ensure_app() -> QApplication:
    global _app
    existing = QApplication.instance()
    if existing is not None:
        return existing  # type: ignore[return-value]
    _app = QApplication([])
    return _app


class TopologyDragTests(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()

    def _make(self, rows: int = 3, cols: int = 3, order=None, occupied=None):
        return TopologyDialog(
            slave_grid_rows=rows,
            slave_grid_columns=cols,
            max_selection=rows * cols,
            order=order,
            occupied_cells=occupied,
        )

    def test_press_on_free_plus_drag_adds_four_cells(self) -> None:
        d = self._make()
        d._drag_begin(0)
        d._drag_apply(1)
        d._drag_apply(2)
        d._drag_apply(3)
        d._drag_end()
        self.assertEqual([0, 1, 2, 3], d.order)

    def test_press_on_occupied_plus_drag_removes_three(self) -> None:
        d = self._make(order=[0, 1, 2, 4])
        d._drag_begin(0)
        d._drag_apply(1)
        d._drag_apply(2)
        d._drag_end()
        self.assertEqual([4], d.order)

    def test_press_on_disabled_is_noop(self) -> None:
        d = self._make(occupied={4})
        d._drag_begin(4)
        # Dragging across eligible cells should not apply anything
        # because drag never became active.
        d._drag_apply(0)
        d._drag_apply(1)
        d._drag_end()
        self.assertEqual([], d.order)
        self.assertFalse(d._drag_active)

    def test_drag_crosses_disabled_sibling_cell_skipped(self) -> None:
        d = self._make(occupied={4})
        d._drag_begin(0)
        d._drag_apply(4)  # occupied sibling -> skipped silently
        d._drag_apply(5)
        d._drag_end()
        self.assertEqual([0, 5], d.order)

    def test_drag_revisits_same_cell_no_double_toggle(self) -> None:
        d = self._make()
        d._drag_begin(0)
        d._drag_apply(1)
        d._drag_apply(0)  # revisit press cell
        d._drag_apply(1)  # revisit
        d._drag_end()
        self.assertEqual([0, 1], d.order)


class LedWireDragTests(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()

    def _make(
        self,
        rows: int = 3,
        cols: int = 3,
        led_count: int = 6,
        initial=None,
    ):
        return LedWireDialog(
            canvas_rows=rows,
            canvas_cols=cols,
            led_count=led_count,
            initial_cells=initial,
        )

    def test_left_drag_assigns_consecutive_indices(self) -> None:
        d = self._make(led_count=4)
        d._drag_begin(0, shift=False)
        d._drag_apply(1)
        d._drag_apply(2)
        d._drag_apply(3)
        d._drag_end()
        self.assertEqual([0, 1, 2, 3], d._order)

    def test_shift_drag_removes_assigned_cells(self) -> None:
        d = self._make(led_count=4, initial=[0, 1, 2, 3])
        d._drag_begin(0, shift=True)
        d._drag_apply(1)
        d._drag_apply(2)
        d._drag_end()
        self.assertEqual([3], d._order)

    def test_drag_invalid_rolls_back_changes(self) -> None:
        d = self._make(led_count=4)
        d._drag_begin(0, shift=False)
        d._drag_apply(1)
        d._drag_apply(2)
        # Force validation to fail to exercise rollback.
        import ProjectScreen.PlateLogic.LedWireDialog as mod

        original = mod.validate_wire_assignment

        def fake_validate(cells, canvas, led_count):
            return ["forced failure"]

        mod.validate_wire_assignment = fake_validate
        # Also patch QMessageBox.warning to avoid modal dialog.
        from PyQt6.QtWidgets import QMessageBox

        orig_warn = QMessageBox.warning
        QMessageBox.warning = staticmethod(lambda *a, **k: 0)  # type: ignore[assignment]
        try:
            d._drag_end()
        finally:
            mod.validate_wire_assignment = original
            QMessageBox.warning = orig_warn  # type: ignore[assignment]
        self.assertEqual([], d._order)

    def test_drag_crosses_already_assigned_cell_skipped(self) -> None:
        d = self._make(led_count=4, initial=[2])
        d._drag_begin(0, shift=False)
        d._drag_apply(1)
        d._drag_apply(2)  # already assigned -> skipped
        d._drag_apply(3)
        d._drag_end()
        self.assertEqual([2, 0, 1, 3], d._order)


class TagPinsDragTests(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()

    def _make(self, topology=None, cols: int = 3):
        if topology is None:
            topology = [0, 1, 2, 3, 4, 5]
        return TagPinsDialog(
            topology=topology,
            slave_grid_columns=cols,
            current_colors=[],
        )

    def test_left_drag_paints_four_cells_with_current_color(self) -> None:
        d = self._make(topology=[0, 1, 3, 4], cols=3)
        d._color_picker.setColor([10, 20, 30])
        d._drag_begin(0, "left")
        d._drag_apply(1)
        d._drag_apply(2)
        d._drag_apply(3)
        d._drag_end()
        self.assertEqual([[10, 20, 30]] * 4, d.colors)

    def test_right_drag_clears_colored_cells(self) -> None:
        d = self._make(topology=[0, 1, 3], cols=3)
        d._color_picker.setColor([200, 100, 50])
        d._drag_begin(0, "left")
        d._drag_apply(1)
        d._drag_apply(2)
        d._drag_end()
        self.assertEqual([[200, 100, 50]] * 3, d.colors)
        d._drag_begin(0, "right")
        d._drag_apply(1)
        d._drag_end()
        self.assertEqual(
            [[0, 0, 0], [0, 0, 0], [200, 100, 50]],
            d.colors,
        )

    def test_drag_crosses_gap_cell_skipped(self) -> None:
        # Topology occupies topo positions 0 (cell 0), 1 (cell 2).
        # Bbox spans cells 0, 1, 2; cell 1 is a gap.
        d = self._make(topology=[0, 2], cols=3)
        d._color_picker.setColor([5, 6, 7])
        # Enabled buttons are keyed by topology pos 0 and 1. Pos -1
        # / "gap" cells never reach _drag_apply via the eventFilter;
        # for the programmatic test we simulate the routing skip by
        # asserting only valid positions get painted.
        self.assertIn(0, d._buttons_by_pos)
        self.assertIn(1, d._buttons_by_pos)
        d._drag_begin(0, "left")
        d._drag_apply(1)
        d._drag_end()
        self.assertEqual([[5, 6, 7], [5, 6, 7]], d.colors)


if __name__ == "__main__":
    unittest.main()
