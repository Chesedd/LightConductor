"""Tests for the unified Tag editor popout (Phase 10.1).

Headless-Qt tests that drive :class:`TagPinsDialog` directly against a
minimal ``ProjectWindow``-shaped stub. The fakes mirror what
``set_active_slave`` and :mod:`ProjectScreen.TagLogic.TagManager`
expose at runtime — enough for the window to rebind its grid + preview,
enable/disable the ``Place tag`` button, and push an
``AddOrReplaceTagCommand`` through the real ``CommandStack``. Visual
confirmation (real window surface, preview colors, dropdown toggles)
requires a local Qt session and is out of scope for CI.
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

from types import SimpleNamespace  # noqa: E402

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMainWindow  # noqa: E402

from lightconductor.application.commands import CommandStack  # noqa: E402
from lightconductor.application.project_state import (  # noqa: E402
    ProjectState,
)
from lightconductor.domain.models import (  # noqa: E402
    Master,
    Slave,
    TagType,
)
from ProjectScreen.PlateLogic.TagPinsDialog import (  # noqa: E402
    TagPinsDialog,
)

_app: QApplication | None = None


def _ensure_app() -> QApplication:
    global _app
    existing = QApplication.instance()
    if existing is not None:
        return existing  # type: ignore[return-value]
    _app = QApplication([])
    return _app


class FakeManager(QObject):
    currentTypeChanged = pyqtSignal(object)

    def __init__(self, cur_type: object = None) -> None:
        super().__init__()
        self.curType = cur_type

    def set_cur_type(self, cur_type: object) -> None:
        self.curType = cur_type
        self.currentTypeChanged.emit(cur_type)


class FakeRenderer:
    def __init__(self, value: float = 0.0, duration: float = 10.0) -> None:
        self.duration = duration
        self.selectedLine = SimpleNamespace(value=lambda v=value: v)

    def set_time(self, value: float) -> None:
        self.selectedLine = SimpleNamespace(value=lambda v=value: v)


class FakeWave:
    def __init__(self, manager: FakeManager, renderer: FakeRenderer) -> None:
        self.manager = manager
        self._renderer = renderer


class FakeSlaveBox:
    def __init__(
        self,
        *,
        master_id: str,
        slave_id: str,
        title: str,
        cur_type: object = None,
        time_value: float = 0.0,
        grid_columns: int = 2,
        led_cells: list[int] | None = None,
    ) -> None:
        self._master_id = master_id
        self.boxID = slave_id
        self.title = title
        self._grid_columns = grid_columns
        self._led_cells = list(led_cells or [0, 1])
        self.wave = FakeWave(
            manager=FakeManager(cur_type=cur_type),
            renderer=FakeRenderer(value=time_value),
        )


class MiniProjectWindow(QMainWindow):
    activeSlaveChanged = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.state = ProjectState()
        self.commands = CommandStack(self.state)
        self._active_slave: FakeSlaveBox | None = None
        self._tag_pins_window: TagPinsDialog | None = None

    def set_active_slave(self, slave: FakeSlaveBox | None) -> None:
        self._active_slave = slave
        self.activeSlaveChanged.emit(slave)

    def showTagEditorWindow(self) -> None:
        if self._tag_pins_window is not None:
            self._tag_pins_window.raise_()
            self._tag_pins_window.activateWindow()
            return
        window = TagPinsDialog(project_window=self, parent=self)
        self._tag_pins_window = window
        window.destroyed.connect(self._on_destroyed)
        window.show()

    def _on_destroyed(self, _obj: object = None) -> None:
        self._tag_pins_window = None


def _seed(
    state: ProjectState,
    master_id: str,
    slave_id: str,
    type_name: str,
) -> TagType:
    tt = TagType(
        name=type_name,
        pin="1",
        rows=1,
        columns=2,
        topology=[0, 1],
    )
    slave = Slave(
        id=slave_id,
        name=f"slave-{slave_id}",
        pin="1",
        led_count=2,
        grid_rows=1,
        grid_columns=2,
        led_cells=[0, 1],
        tag_types={type_name: tt},
    )
    master = Master(id=master_id, name="m", ip="127.0.0.1", slaves={slave_id: slave})
    state.load_masters({master_id: master})
    return tt


class _WidgetCurType:
    """Stand-in for the widget-side ``TagType`` produced by
    :class:`TagManager`. The dialog only reads ``name``, ``topology``,
    and ``table`` off ``curType``."""

    def __init__(self, name: str, topology: list[int], table: int = 2) -> None:
        self.name = name
        self.topology = list(topology)
        self.table = table


class TagPinsWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.pw = MiniProjectWindow()
        _seed(self.pw.state, "m1", "s1", "alpha")
        self.cur_type = _WidgetCurType("alpha", [0, 1])
        self.slave = FakeSlaveBox(
            master_id="m1",
            slave_id="s1",
            title="Alpha",
            cur_type=self.cur_type,
            time_value=1.0,
        )

    def tearDown(self) -> None:
        win = self.pw._tag_pins_window
        if win is not None:
            win.close()
            QApplication.processEvents()
        self.pw.close()

    def _tags(self, type_name: str = "alpha") -> list:
        return self.pw.state.master("m1").slaves["s1"].tag_types[type_name].tags

    def test_opens_with_expected_widgets(self) -> None:
        self.pw.set_active_slave(self.slave)
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        self.assertIsNotNone(win)
        assert win is not None
        self.assertEqual(["On", "Off"], [win.state_bar().itemText(i) for i in range(2)])
        self.assertTrue(win.place_button().isVisible())

    def test_second_click_raises_existing_window(self) -> None:
        self.pw.showTagEditorWindow()
        first = self.pw._tag_pins_window
        self.pw.showTagEditorWindow()
        second = self.pw._tag_pins_window
        self.assertIs(first, second)

    def test_close_clears_reference_and_reopen_is_fresh(self) -> None:
        self.pw.showTagEditorWindow()
        first = self.pw._tag_pins_window
        assert first is not None
        first.close()
        for _ in range(5):
            QApplication.processEvents()
        self.assertIsNone(self.pw._tag_pins_window)
        self.pw.showTagEditorWindow()
        second = self.pw._tag_pins_window
        self.assertIsNotNone(second)
        self.assertIsNot(first, second)

    def test_place_disabled_when_no_active_slave(self) -> None:
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        assert win is not None
        self.assertFalse(win.place_button().isEnabled())

    def test_place_disabled_when_no_cur_type(self) -> None:
        slave_no_type = FakeSlaveBox(
            master_id="m1",
            slave_id="s1",
            title="Alpha",
            cur_type=None,
        )
        self.pw.set_active_slave(slave_no_type)
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        assert win is not None
        self.assertFalse(win.place_button().isEnabled())

    def test_active_slave_change_enables_place(self) -> None:
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        assert win is not None
        self.assertFalse(win.place_button().isEnabled())
        self.pw.set_active_slave(self.slave)
        self.assertTrue(win.place_button().isEnabled())

    def test_cur_type_cleared_disables_place(self) -> None:
        self.pw.set_active_slave(self.slave)
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        assert win is not None
        self.assertTrue(win.place_button().isEnabled())
        self.slave.wave.manager.set_cur_type(None)
        self.assertFalse(win.place_button().isEnabled())

    def test_state_dropdown_flips_action_on(self) -> None:
        self.pw.set_active_slave(self.slave)
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        assert win is not None
        win.state_bar().setCurrentText("Off")
        self.assertFalse(win._action_on)
        win.state_bar().setCurrentText("On")
        self.assertTrue(win._action_on)

    def test_place_tag_creates_domain_tag(self) -> None:
        self.pw.set_active_slave(self.slave)
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        assert win is not None
        self.assertEqual([], self._tags())
        win.place_button().click()
        tags = self._tags()
        self.assertEqual(1, len(tags))
        self.assertEqual(1.0, tags[0].time_seconds)
        self.assertTrue(bool(tags[0].action))

    def test_place_tag_twice_at_same_time_replaces_atomically(self) -> None:
        self.pw.set_active_slave(self.slave)
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        assert win is not None

        win.state_bar().setCurrentText("On")
        win.place_button().click()
        first_tags = list(self._tags())
        self.assertEqual(1, len(first_tags))
        original = first_tags[0]

        win.state_bar().setCurrentText("Off")
        win.place_button().click()
        second_tags = self._tags()
        self.assertEqual(1, len(second_tags))
        self.assertIsNot(original, second_tags[0])
        self.assertFalse(bool(second_tags[0].action))

        self.pw.commands.undo()
        restored = self._tags()
        self.assertEqual(1, len(restored))
        self.assertIs(original, restored[0])
        self.assertTrue(bool(restored[0].action))


if __name__ == "__main__":
    unittest.main()
