"""Headless-Qt tests for wheel zoom + scroll behavior in
:class:`TopologyDialog` (Phase 12.1).

Drag-paint coverage lives in ``tests/test_drag_paint.py``. This file
targets the Phase 12.1 zoom state machine: ``_cell_size``,
``_user_zoomed``, and the ``resizeEvent`` / ``_on_wheel_zoom``
interaction. Mirrors ``tests/test_led_wire_dialog.py`` for the
LedWireDialog Phase 12 feature.
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

from PyQt6.QtWidgets import QApplication  # noqa: E402

from ProjectScreen.TagLogic.TagManager import TopologyDialog  # noqa: E402

_app: QApplication | None = None


def _ensure_app() -> QApplication:
    global _app
    existing = QApplication.instance()
    if existing is not None:
        return existing  # type: ignore[return-value]
    _app = QApplication([])
    return _app


class TopologyDialogZoomTests(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()

    def _make(
        self,
        rows: int = 4,
        cols: int = 4,
        max_selection: int = 8,
    ) -> TopologyDialog:
        return TopologyDialog(
            slave_grid_rows=rows,
            slave_grid_columns=cols,
            max_selection=max_selection,
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

    def test_wheel_zoom_out_clamps_at_min(self) -> None:
        """Wheel-out beyond the min clamp stops at ``DEFAULT_MIN_CELL``
        (6) — the grid does not shrink unboundedly per tick."""
        d = self._make()
        for _ in range(40):
            d._on_wheel_zoom(-120)
        self.assertEqual(6, d._cell_size)

    def test_resize_after_user_zoom_does_not_refit(self) -> None:
        """After the first wheel tick, later dialog resizes must not
        re-fit the grid back to viewport size — the user's pinned
        cell size sticks until the dialog is closed and reopened."""
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

    def test_drag_still_works_after_wheel_zoom_in(self) -> None:
        """Zooming in grows the grid past the viewport; drag-paint
        still routes through the same ``_drag_*`` API regardless of
        cell size or scroll offset, so the resulting order is
        identical to the unzoomed case."""
        d = self._make(rows=3, cols=3, max_selection=9)
        d._on_wheel_zoom(120)
        d._on_wheel_zoom(120)
        d._on_wheel_zoom(120)
        self.assertTrue(d._user_zoomed)
        self.assertGreater(d._cell_size, 6)
        d._drag_begin(0)
        d._drag_apply(1)
        d._drag_apply(2)
        d._drag_apply(3)
        d._drag_end()
        self.assertEqual([0, 1, 2, 3], d.order)


if __name__ == "__main__":
    unittest.main()
