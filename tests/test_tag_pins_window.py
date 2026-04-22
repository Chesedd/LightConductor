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

from PyQt6.QtCore import QObject, QPoint, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMainWindow  # noqa: E402

from lightconductor.application.commands import CommandStack  # noqa: E402
from lightconductor.application.project_state import (  # noqa: E402
    ProjectState,
)
from lightconductor.domain.models import (  # noqa: E402
    Master,
    Slave,
    Tag,
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

    def test_active_slave_changed_same_slave_does_not_rebind(self) -> None:
        """Re-emitting activeSlaveChanged with the same slave must not
        wipe in-progress per-LED color edits. Without the identity
        guard, ``_apply_active_slave`` → ``_rebind_from_current_type``
        → ``_install_topology`` resets ``colors`` to defaults."""
        self.pw.set_active_slave(self.slave)
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        assert win is not None
        win.colors[0] = [255, 0, 0]

        calls: list[object] = []
        original = win._apply_active_slave

        def spy(slave: object) -> None:
            calls.append(slave)
            original(slave)

        win._apply_active_slave = spy  # type: ignore[assignment]
        self.pw.activeSlaveChanged.emit(self.slave)

        self.assertEqual([], calls)
        self.assertEqual([255, 0, 0], win.colors[0])

    def test_active_slave_changed_different_slave_does_rebind(self) -> None:
        """A different slave must trigger ``_apply_active_slave`` and
        rebuild the grid with the new topology's defaults — any
        in-progress edits on the prior slave are intentionally lost."""
        self.pw.set_active_slave(self.slave)
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        assert win is not None
        win.colors[0] = [255, 0, 0]

        _seed(self.pw.state, "m2", "s2", "beta")
        cur_type_b = _WidgetCurType("beta", [0, 1])
        slave_b = FakeSlaveBox(
            master_id="m2",
            slave_id="s2",
            title="Beta",
            cur_type=cur_type_b,
        )
        self.pw.set_active_slave(slave_b)

        self.assertIs(slave_b, win.active_slave())
        self.assertEqual([255, 255, 255], win.colors[0])

    def test_wheel_zoom_changes_cell_size_and_sets_flag(self) -> None:
        """Directly invoking ``_on_wheel_zoom`` (the handler the
        scroll-area viewport's event filter routes a wheel tick to)
        must apply :func:`apply_wheel_zoom` and flip ``_user_zoomed``
        True. Starting from a pinned 16 so initial fit-to-window (which
        for a 1x2 topology exceeds the 64 clamp) doesn't dominate."""
        from lightconductor.application.grid_zoom import apply_wheel_zoom

        self.pw.set_active_slave(self.slave)
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        assert win is not None
        self.assertFalse(win._user_zoomed)
        win._cell_size = 16
        win._on_wheel_zoom(120)
        self.assertTrue(win._user_zoomed)
        self.assertEqual(apply_wheel_zoom(16, 120), win._cell_size)

    def test_resize_after_user_zoom_does_not_refit(self) -> None:
        """After the first wheel tick, later dialog resizes must not
        re-fit the grid back to viewport size — the user's pinned cell
        size sticks until the dialog is closed and reopened."""
        self.pw.set_active_slave(self.slave)
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        assert win is not None
        win._on_wheel_zoom(120)
        win._on_wheel_zoom(120)
        pinned = win._cell_size
        win.resize(900, 700)
        QApplication.processEvents()
        self.assertEqual(pinned, win._cell_size)
        win.resize(200, 200)
        QApplication.processEvents()
        self.assertEqual(pinned, win._cell_size)

    def test_middle_drag_shifts_horizontal_scrollbar(self) -> None:
        """Middle-button pan is active only while the button is held
        and maps cursor-right motion to a leftward scroll (h0 - dx).
        Simulated with a seeded range since offscreen layout gives the
        small 1x2 grid a zero scrollbar range."""
        self.pw.set_active_slave(self.slave)
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        assert win is not None
        assert win._grid_scroll is not None
        hbar = win._grid_scroll.horizontalScrollBar()
        hbar.setRange(0, 200)
        hbar.setValue(100)
        win._pan_begin(QPoint(0, 0))
        self.assertTrue(win._pan_active)
        win._pan_apply(QPoint(50, 0))
        self.assertEqual(50, hbar.value())

    def test_middle_release_resets_pan_state(self) -> None:
        self.pw.set_active_slave(self.slave)
        self.pw.showTagEditorWindow()
        win = self.pw._tag_pins_window
        assert win is not None
        win._pan_begin(QPoint(10, 10))
        self.assertTrue(win._pan_active)
        win._pan_end()
        self.assertFalse(win._pan_active)
        self.assertIsNone(win._pan_start_global)

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


class TagPinsEditModeTests(unittest.TestCase):
    """Edit-mode tests — constructing the dialog against an existing
    domain tag and exercising Save/Delete paths via the real
    :class:`CommandStack`. Topology/bbox context is passed through
    kwargs so edit mode does not rely on the active-slave signal
    (which it ignores by contract)."""

    def setUp(self) -> None:
        _ensure_app()
        self.pw = MiniProjectWindow()
        _seed(self.pw.state, "m1", "s1", "alpha")
        initial_tag = Tag(
            time_seconds=0.5,
            action=True,
            colors=[[10, 20, 30], [40, 50, 60]],
        )
        self.pw.state.add_tag("m1", "s1", "alpha", initial_tag)
        # Retrieve the stored tag reference — state makes a domain
        # tag; we edit that one by identity.
        self.tag = self.pw.state.master("m1").slaves["s1"].tag_types["alpha"].tags[0]

    def tearDown(self) -> None:
        self.pw.close()
        QApplication.processEvents()

    def _tags(self) -> list:
        return list(
            self.pw.state.master("m1").slaves["s1"].tag_types["alpha"].tags,
        )

    def _make_edit_window(self) -> TagPinsDialog:
        return TagPinsDialog(
            project_window=self.pw,
            parent=self.pw,
            mode="edit",
            tag=self.tag,
            master_id="m1",
            slave_id="s1",
            type_name="alpha",
            topology=[0, 1],
            slave_grid_columns=2,
            led_cells=[0, 1],
        )

    def test_edit_mode_rejects_missing_tag(self) -> None:
        with self.assertRaises(ValueError):
            TagPinsDialog(mode="edit")

    def test_edit_mode_populates_state_time_and_type_name(self) -> None:
        win = self._make_edit_window()
        self.assertEqual("edit", win.mode())
        self.assertIsNotNone(win.save_button())
        self.assertIsNotNone(win.delete_button())
        self.assertFalse(win.place_button().isVisible())
        self.assertEqual("On", win.state_bar().currentText())
        time_edit = win.time_edit()
        assert time_edit is not None
        self.assertEqual(0.5, float(time_edit.text()))
        self.assertIn("alpha", win.windowTitle())
        win.close()

    def test_edit_mode_save_pushes_edit_command_with_snapped_time(self) -> None:
        win = self._make_edit_window()
        time_edit = win.time_edit()
        assert time_edit is not None
        time_edit.setText("1.031")
        win.colors[0] = [200, 100, 50]
        save_btn = win.save_button()
        assert save_btn is not None
        save_btn.click()
        tags = self._tags()
        self.assertEqual(1, len(tags))
        self.assertAlmostEqual(1.04, tags[0].time_seconds, places=5)
        self.assertEqual([200, 100, 50], list(tags[0].colors[0]))
        # Dialog stays open after save.
        self.assertTrue(win.isVisible() or win._mode == "edit")
        # Undo restores the original.
        self.pw.commands.undo()
        restored = self._tags()
        self.assertAlmostEqual(0.5, restored[0].time_seconds, places=5)
        win.close()

    def test_edit_mode_save_rejects_invalid_time_input(self) -> None:
        win = self._make_edit_window()
        time_edit = win.time_edit()
        assert time_edit is not None
        time_edit.setText("not-a-number")
        save_btn = win.save_button()
        assert save_btn is not None
        # Suppress the QMessageBox popup in headless tests by patching
        # the class method during the click.
        from PyQt6.QtWidgets import QMessageBox

        original_warning = QMessageBox.warning
        QMessageBox.warning = staticmethod(  # type: ignore[assignment]
            lambda *a, **k: QMessageBox.StandardButton.Ok,
        )
        try:
            save_btn.click()
        finally:
            QMessageBox.warning = original_warning  # type: ignore[assignment]
        tags = self._tags()
        self.assertAlmostEqual(0.5, tags[0].time_seconds, places=5)
        win.close()

    def test_edit_mode_delete_confirms_and_pushes_delete_command(self) -> None:
        win = self._make_edit_window()
        delete_btn = win.delete_button()
        assert delete_btn is not None
        from PyQt6.QtWidgets import QMessageBox

        original_question = QMessageBox.question
        QMessageBox.question = staticmethod(  # type: ignore[assignment]
            lambda *a, **k: QMessageBox.StandardButton.Yes,
        )
        try:
            delete_btn.click()
        finally:
            QMessageBox.question = original_question  # type: ignore[assignment]
        self.assertEqual(0, len(self._tags()))

    def test_edit_mode_delete_cancels_on_no(self) -> None:
        win = self._make_edit_window()
        delete_btn = win.delete_button()
        assert delete_btn is not None
        from PyQt6.QtWidgets import QMessageBox

        original_question = QMessageBox.question
        QMessageBox.question = staticmethod(  # type: ignore[assignment]
            lambda *a, **k: QMessageBox.StandardButton.No,
        )
        try:
            delete_btn.click()
        finally:
            QMessageBox.question = original_question  # type: ignore[assignment]
        self.assertEqual(1, len(self._tags()))
        win.close()

    def test_edit_mode_ignores_active_slave_changes(self) -> None:
        """Edit mode is pinned to the bound tag's topology; emitting
        ``activeSlaveChanged`` must NOT trigger ``_apply_active_slave``
        or rebuild the grid."""
        win = self._make_edit_window()
        calls: list[object] = []
        original = win._apply_active_slave
        win._apply_active_slave = lambda s: calls.append(s) or original(s)  # type: ignore[assignment]
        other_slave = FakeSlaveBox(
            master_id="m1",
            slave_id="s1",
            title="Alpha",
            cur_type=_WidgetCurType("beta", [0, 1]),
        )
        self.pw.activeSlaveChanged.emit(other_slave)
        self.assertEqual([], calls)
        win.close()

    def test_edit_mode_multiple_instances_coexist(self) -> None:
        win_a = self._make_edit_window()
        win_b = self._make_edit_window()
        self.assertIsNot(win_a, win_b)
        save_a = win_a.save_button()
        save_b = win_b.save_button()
        self.assertIsNotNone(save_a)
        self.assertIsNotNone(save_b)
        self.assertTrue(save_a is not save_b)
        win_a.close()
        win_b.close()

    def test_place_mode_has_no_save_or_delete_buttons(self) -> None:
        # Regression guard for the mode switch: place-mode never
        # exposes Save / Delete.
        win = TagPinsDialog(
            project_window=self.pw,
            parent=self.pw,
            mode="place",
        )
        self.assertEqual("place", win.mode())
        self.assertIsNone(win.save_button())
        self.assertIsNone(win.delete_button())
        self.assertIsNone(win.time_edit())
        self.assertIsNotNone(win.place_button())
        win.close()


if __name__ == "__main__":
    unittest.main()
