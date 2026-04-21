"""Tests for the popout LED preview window (Phase 9.3).

Headless-Qt tests driving LedPreviewWindow wiring directly. The
tests build a minimal ProjectWindow-shaped stub to avoid pulling in
the full ProjectWindow.__init__ (which loads a project session).
Visual confirmation (actual window appearing, geometry, resizing
cells) requires a local Qt session and is out of scope for CI."""

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

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMainWindow  # noqa: E402

from lightconductor.application.project_state import ProjectState  # noqa: E402
from lightconductor.domain.models import (  # noqa: E402
    Master,
    Slave,
    Tag,
    TagType,
)
from ProjectScreen.PlateLogic.LedPreviewWindow import (  # noqa: E402
    LedPreviewWindow,
)
from ProjectScreen.TagLogic.LedGridView import LedGridView  # noqa: E402

_app: QApplication | None = None


def _ensure_app() -> QApplication:
    global _app
    existing = QApplication.instance()
    if existing is not None:
        return existing  # type: ignore[return-value]
    _app = QApplication([])
    return _app


class FakeWave(QObject):
    positionUpdate = pyqtSignal(float, str)


class FakeSlaveBox:
    """Minimal stand-in for SlaveBox. LedPreviewWindow only needs a
    few attributes: ``_master_id``, ``boxID``, ``title``, ``wave``."""

    def __init__(self, master_id: str, box_id: str, title: str) -> None:
        self._master_id = master_id
        self.boxID = box_id
        self.title = title
        self.wave = FakeWave()


class MiniProjectWindow(QMainWindow):
    """Minimal ProjectWindow surface: the two signals + methods that
    LedPreviewWindow and the popout button handler exercise. Mirrors
    the logic in ProjectWindow.set_active_slave / showLedPreviewWindow
    without pulling in session / audio / validation machinery."""

    activeSlaveChanged = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self._active_slave: FakeSlaveBox | None = None
        self._preview_window: LedPreviewWindow | None = None
        self.state = ProjectState()

    def set_active_slave(self, slave: FakeSlaveBox | None) -> None:
        self._active_slave = slave
        self.activeSlaveChanged.emit(slave)

    def showLedPreviewWindow(self) -> None:
        if self._preview_window is not None:
            self._preview_window.raise_()
            self._preview_window.activateWindow()
            return
        window = LedPreviewWindow(self, parent=self)
        self._preview_window = window
        window.destroyed.connect(self._on_preview_destroyed)
        window.show()

    def _on_preview_destroyed(self, _obj: object = None) -> None:
        self._preview_window = None


def _seed_slave(state: ProjectState, master_id: str, slave_id: str) -> None:
    """Populate the ProjectState with a minimal 2x3 grid slave so the
    LedGridView has something coherent to render."""
    tt = TagType(
        name="alpha",
        pin="1",
        rows=1,
        columns=2,
        topology=[0, 3],
        tags=[
            Tag(
                time_seconds=0.0,
                action=True,
                colors=[[255, 0, 0], [0, 255, 0]],
            ),
        ],
    )
    slave = Slave(
        id=slave_id,
        name=f"slave-{slave_id}",
        pin="1",
        led_count=6,
        grid_rows=2,
        grid_columns=3,
        led_cells=[0, 1, 2, 3, 4, 5],
        tag_types={"alpha": tt},
    )
    master = Master(id=master_id, name="m", ip="127.0.0.1", slaves={slave_id: slave})
    state.load_masters({master_id: master})


class LedPreviewWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.pw = MiniProjectWindow()
        _seed_slave(self.pw.state, "m1", "s1")
        self.slave_a = FakeSlaveBox("m1", "s1", "Alpha slave")

    def tearDown(self) -> None:
        win = self.pw._preview_window
        if win is not None:
            win.close()
            QApplication.processEvents()
        self.pw.close()

    def test_button_click_opens_popout_with_led_grid_view(self) -> None:
        """Opening the preview produces exactly one popout whose
        central widget is a LedGridView."""
        self.pw.set_active_slave(self.slave_a)
        self.pw.showLedPreviewWindow()
        win = self.pw._preview_window
        self.assertIsNotNone(win)
        assert win is not None  # for mypy narrowing in tests
        self.assertIsInstance(win.grid_view(), LedGridView)
        self.assertTrue(win.isVisible())

    def test_second_open_raises_existing_popout_no_duplicate(self) -> None:
        """A second call to showLedPreviewWindow must return the same
        window — no duplicate popouts allowed."""
        self.pw.showLedPreviewWindow()
        first = self.pw._preview_window
        self.pw.showLedPreviewWindow()
        second = self.pw._preview_window
        self.assertIs(first, second)

    def test_close_clears_project_window_reference(self) -> None:
        """Closing the popout must clear ProjectWindow._preview_window
        via the destroyed signal so the next open rebuilds fresh."""
        self.pw.showLedPreviewWindow()
        win = self.pw._preview_window
        self.assertIsNotNone(win)
        assert win is not None
        win.close()
        # Let Qt run deleteLater + destroyed signal emission.
        for _ in range(5):
            QApplication.processEvents()
        self.assertIsNone(self.pw._preview_window)

    def test_slave_change_propagates_to_grid_view(self) -> None:
        """activeSlaveChanged should route through LedPreviewWindow and
        update the internal LedGridView's slave wiring."""
        self.pw.showLedPreviewWindow()
        win = self.pw._preview_window
        assert win is not None
        self.pw.set_active_slave(self.slave_a)
        self.assertEqual("m1", win.grid_view()._master_id)
        self.assertEqual("s1", win.grid_view()._slave_id)
        # Now switch to a different slave.
        _seed_slave(self.pw.state, "m2", "s2")
        slave_b = FakeSlaveBox("m2", "s2", "Beta slave")
        self.pw.set_active_slave(slave_b)
        self.assertEqual("m2", win.grid_view()._master_id)
        self.assertEqual("s2", win.grid_view()._slave_id)

    def test_title_updates_on_slave_change(self) -> None:
        """Window title must include the active slave's display name."""
        self.pw.showLedPreviewWindow()
        win = self.pw._preview_window
        assert win is not None
        self.pw.set_active_slave(self.slave_a)
        self.assertIn("Alpha slave", win.windowTitle())
        slave_b = FakeSlaveBox("m1", "s1", "Renamed slave")
        self.pw.set_active_slave(slave_b)
        self.assertIn("Renamed slave", win.windowTitle())

    def test_reopen_after_close_rebuilds_new_window(self) -> None:
        """After close, the next open must produce a fresh, distinct
        LedPreviewWindow instance (Option B ownership model)."""
        self.pw.showLedPreviewWindow()
        first = self.pw._preview_window
        assert first is not None
        first.close()
        for _ in range(5):
            QApplication.processEvents()
        self.assertIsNone(self.pw._preview_window)
        self.pw.showLedPreviewWindow()
        second = self.pw._preview_window
        self.assertIsNotNone(second)
        self.assertIsNot(first, second)

    def test_position_update_from_active_slave_sets_grid_time(self) -> None:
        """Emitting positionUpdate on the connected slave's wave must
        forward into LedGridView.set_time, advancing the current time."""
        self.pw.set_active_slave(self.slave_a)
        self.pw.showLedPreviewWindow()
        win = self.pw._preview_window
        assert win is not None
        self.assertEqual(0.0, win.grid_view()._current_time)
        self.slave_a.wave.positionUpdate.emit(2.5, "0:02.500")
        self.assertEqual(2.5, win.grid_view()._current_time)

    def test_slave_change_disconnects_prior_position_update(self) -> None:
        """After switching slaves, position ticks from the old slave
        must not bleed into the popout any more."""
        self.pw.set_active_slave(self.slave_a)
        self.pw.showLedPreviewWindow()
        win = self.pw._preview_window
        assert win is not None
        _seed_slave(self.pw.state, "m2", "s2")
        slave_b = FakeSlaveBox("m2", "s2", "Beta slave")
        self.pw.set_active_slave(slave_b)
        # Baseline after switch: current_time reset via _recompute is
        # not guaranteed, so capture and compare against the stale
        # emit from slave_a.
        before = win.grid_view()._current_time
        self.slave_a.wave.positionUpdate.emit(9.75, "0:09.750")
        self.assertEqual(before, win.grid_view()._current_time)


if __name__ == "__main__":
    unittest.main()
