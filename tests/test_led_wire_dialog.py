"""Headless-Qt tests for wheel zoom + scroll behavior in
:class:`LedWireDialog`. Drag-paint coverage lives in
``tests/test_drag_paint.py``; wire-assignment math lives in
``tests/test_wire_assignment.py``. This file targets the Phase 12
zoom state machine: ``_cell_size``, ``_user_zoomed``, and the
``resizeEvent`` / ``_on_wheel_zoom`` interaction.
"""

from __future__ import annotations

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

from PyQt6.QtCore import QPoint  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from ProjectScreen.PlateLogic.LedWireDialog import LedWireDialog  # noqa: E402

_app: QApplication | None = None


def _ensure_app() -> QApplication:
    global _app
    existing = QApplication.instance()
    if existing is not None:
        return existing  # type: ignore[return-value]
    _app = QApplication([])
    return _app


class LedWireDialogZoomTests(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()

    def _make(
        self,
        rows: int = 4,
        cols: int = 4,
        led_count: int = 8,
    ) -> LedWireDialog:
        return LedWireDialog(
            canvas_rows=rows,
            canvas_cols=cols,
            led_count=led_count,
        )

    def test_wheel_zoom_applies_helper_and_sets_flag(self) -> None:
        from lightconductor.application.grid_zoom import apply_wheel_zoom

        d = self._make()
        self.assertFalse(d._user_zoomed)
        # Pin a known starting size so the assertion doesn't depend
        # on platform-specific initial viewport fit geometry.
        d._cell_size = 16
        d._on_wheel_zoom(120)
        self.assertTrue(d._user_zoomed)
        self.assertEqual(apply_wheel_zoom(16, 120), d._cell_size)

    def test_wheel_zoom_out_shrinks_cell_size(self) -> None:
        d = self._make()
        d._cell_size = 40
        d._user_zoomed = True
        d._on_wheel_zoom(-120)
        self.assertLess(d._cell_size, 40)

    def test_resize_after_user_zoom_does_not_refit(self) -> None:
        d = self._make()
        d._on_wheel_zoom(120)
        d._on_wheel_zoom(120)
        pinned = d._cell_size
        d.resize(800, 600)
        QApplication.processEvents()
        self.assertEqual(pinned, d._cell_size)
        d.resize(200, 200)
        QApplication.processEvents()
        self.assertEqual(pinned, d._cell_size)

    def test_cell_size_clamped_to_max(self) -> None:
        """Wheel-in beyond the max clamp stops at ``DEFAULT_MAX_CELL``
        (64) — the grid does not grow unboundedly per tick."""
        d = self._make()
        for _ in range(40):
            d._on_wheel_zoom(120)
        self.assertEqual(64, d._cell_size)

    def test_cell_size_clamped_to_min(self) -> None:
        d = self._make()
        for _ in range(40):
            d._on_wheel_zoom(-120)
        self.assertEqual(6, d._cell_size)


class LedWireDialogPanTests(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()

    def _make(self) -> LedWireDialog:
        return LedWireDialog(canvas_rows=4, canvas_cols=4, led_count=8)

    def test_middle_drag_shifts_horizontal_scrollbar(self) -> None:
        d = self._make()
        hbar = d._scroll.horizontalScrollBar()
        # Simulate a zoomed, scrollable state regardless of headless
        # viewport geometry: give the scrollbar a non-trivial range
        # and initial offset.
        hbar.setRange(0, 200)
        hbar.setValue(100)
        d._pan_begin(QPoint(0, 0))
        self.assertTrue(d._pan_active)
        # Cursor moves 50 px right → scrollbar value = h0 - 50.
        d._pan_apply(QPoint(50, 0))
        self.assertEqual(50, hbar.value())

    def test_middle_release_resets_pan_state(self) -> None:
        d = self._make()
        d._pan_begin(QPoint(10, 10))
        self.assertTrue(d._pan_active)
        d._pan_end()
        self.assertFalse(d._pan_active)
        self.assertIsNone(d._pan_start_global)


if __name__ == "__main__":
    unittest.main()
