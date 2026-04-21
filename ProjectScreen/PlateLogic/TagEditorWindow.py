"""Non-modal, singleton popout that replaces the per-slave ``Add tag``
button. The window mirrors the contents of the legacy ``TagDialog``
(state dropdown, per-LED color editor, LED preview) but is decoupled
from any specific wave: it follows ``ProjectWindow.activeSlaveChanged``
and reads the active slave's ``wave.manager.curType`` at Place-time.

Clicking ``Place tag`` reads the active slave's playhead from
``wave._renderer.selectedLine.value()`` and pushes an
``AddOrReplaceTagCommand`` so that a second click at the same stored
timestamp atomically replaces the prior tag of the same ``TagType``
(one undo reverts the replace). The window never closes itself — the
user closes it via the window-manager close button, at which point
``WA_DeleteOnClose`` tears it down and ``destroyed`` clears the
singleton reference on ``ProjectWindow``.
"""

from __future__ import annotations

from typing import Any, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lightconductor.application.commands import AddOrReplaceTagCommand
from lightconductor.application.pattern_service import PatternService
from lightconductor.domain.models import Tag as DomainTag
from ProjectScreen.PlateLogic.TagPinsDialog import TagPinsDialog
from ProjectScreen.TagLogic.LedGridView import LedGridView

_pattern_service = PatternService()


class TagEditorWindow(QDialog):
    """Popout Tag editor. Follows the project's active slave / current
    TagType and places a tag at the active slave's playhead when the
    user clicks ``Place tag``. Replaces the per-slave ``Add tag``
    button from phase 9.x and earlier."""

    def __init__(self, project_window: Any, parent: Any = None) -> None:
        super().__init__(parent if parent is not None else project_window)
        self._project_window = project_window
        self._active_slave: Any = None
        self._connected_manager: Any = None
        self._action_on: bool = True
        self._colors: List[List[int]] = []

        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("Tag editor")

        self._build_ui()

        signal = getattr(project_window, "activeSlaveChanged", None)
        if signal is not None:
            signal.connect(self._on_active_slave_changed)

        self._apply_active_slave(getattr(project_window, "_active_slave", None))

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self._preview = LedGridView(
            state=None,
            master_id=None,
            slave_id=None,
            parent=self,
            resizable=True,
        )
        root.addWidget(self._preview)

        state_row = QWidget()
        state_layout = QHBoxLayout(state_row)
        state_layout.setContentsMargins(0, 0, 0, 0)
        state_layout.addWidget(QLabel("Состояние"))
        self._state_bar = QComboBox()
        self._state_bar.addItems(["On", "Off"])
        self._state_bar.currentTextChanged.connect(self._on_state_changed)
        state_layout.addWidget(self._state_bar)
        root.addWidget(state_row)

        self._edit_colors_btn = QPushButton("Edit per-LED colors...")
        self._edit_colors_btn.clicked.connect(self._open_pins_dialog)
        root.addWidget(self._edit_colors_btn)

        self._hint_label = QLabel("")
        self._hint_label.setStyleSheet("color: #888;")
        root.addWidget(self._hint_label)

        self._place_btn = QPushButton("Place tag")
        self._place_btn.clicked.connect(self._on_place_tag_clicked)
        root.addWidget(self._place_btn)

    def _on_active_slave_changed(self, slave: Any) -> None:
        self._apply_active_slave(slave)

    def _apply_active_slave(self, slave: Any) -> None:
        if self._connected_manager is not None:
            try:
                self._connected_manager.currentTypeChanged.disconnect(
                    self._on_current_type_changed,
                )
            except (TypeError, RuntimeError):
                pass
            self._connected_manager = None

        self._active_slave = slave
        manager = None
        if slave is not None:
            wave = getattr(slave, "wave", None)
            manager = getattr(wave, "manager", None) if wave is not None else None
        if manager is not None and hasattr(manager, "currentTypeChanged"):
            manager.currentTypeChanged.connect(self._on_current_type_changed)
            self._connected_manager = manager

        self._rebind_from_current_type()

    def _on_current_type_changed(self, _new_type: Any) -> None:
        self._rebind_from_current_type()

    def _current_type(self) -> Any:
        slave = self._active_slave
        if slave is None:
            return None
        wave = getattr(slave, "wave", None)
        manager = getattr(wave, "manager", None) if wave is not None else None
        return getattr(manager, "curType", None) if manager is not None else None

    def _rebind_from_current_type(self) -> None:
        cur_type = self._current_type()
        if cur_type is None:
            self._colors = []
            self._place_btn.setEnabled(False)
            self._edit_colors_btn.setEnabled(False)
            self._hint_label.setText("No tag type selected")
            self._preview.set_buffer([])
            slave_name = getattr(self._active_slave, "title", None)
            if slave_name:
                self.setWindowTitle(f"Tag editor — {slave_name}")
            else:
                self.setWindowTitle("Tag editor")
            return
        topology = list(getattr(cur_type, "topology", []) or [])
        self._colors = [[255, 255, 255] for _ in topology]
        self._hint_label.setText("")
        self._place_btn.setEnabled(True)
        self._edit_colors_btn.setEnabled(self._action_on)
        type_name = getattr(cur_type, "name", "")
        slave_name = getattr(self._active_slave, "title", "") or ""
        if slave_name and type_name:
            self.setWindowTitle(f"Tag editor — {slave_name} / {type_name}")
        elif type_name:
            self.setWindowTitle(f"Tag editor — {type_name}")
        else:
            self.setWindowTitle("Tag editor")
        self._refresh_preview()

    def _on_state_changed(self, state: str) -> None:
        self._action_on = state == "On"
        self._edit_colors_btn.setEnabled(
            self._action_on and self._current_type() is not None
        )
        self._refresh_preview()

    def _open_pins_dialog(self) -> None:
        cur_type = self._current_type()
        if cur_type is None:
            return
        topology = list(getattr(cur_type, "topology", []) or [])
        if not topology:
            return
        slave = self._active_slave
        slave_cols = int(getattr(slave, "_grid_columns", 0) or 0) if slave else 0
        if slave_cols < 1:
            slave_cols = max(1, int(getattr(cur_type, "table", 1) or 1))
        led_cells_attr = (
            getattr(slave, "_led_cells", None) if slave is not None else None
        )
        led_cells = (
            frozenset(int(c) for c in led_cells_attr) if led_cells_attr else None
        )
        settings = None
        on_presets_changed = None
        project_window = self._project_window
        if project_window is not None:
            settings = getattr(project_window, "settings", None)
            on_presets_changed = getattr(project_window, "update_color_presets", None)
        dialog = TagPinsDialog(
            topology=topology,
            slave_grid_columns=slave_cols,
            current_colors=self._colors,
            led_cells=led_cells,
            settings=settings,
            on_presets_changed=on_presets_changed,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._colors = [list(c) for c in dialog.colors]
            self._refresh_preview()

    def _domain_slave(self) -> Any:
        slave = self._active_slave
        state = getattr(self._project_window, "state", None)
        if slave is None or state is None:
            return None
        master_id = getattr(slave, "_master_id", None)
        slave_id = getattr(slave, "boxID", None)
        if master_id is None or slave_id is None:
            return None
        try:
            return state.master(master_id).slaves[slave_id]
        except KeyError:
            return None

    def _refresh_preview(self) -> None:
        cur_type = self._current_type()
        if cur_type is None:
            self._preview.set_buffer([])
            return
        from lightconductor.application.led_preview import (
            render_canvas_with_overlay,
        )

        if self._action_on:
            colors = [list(c) for c in self._colors]
        else:
            colors = [[0, 0, 0] for _ in (self._colors or [])]
        slave = self._domain_slave()
        if slave is None:
            self._preview.set_buffer([])
            return
        current_time = self._playhead_time(clamp=True)
        buffer = render_canvas_with_overlay(
            slave=slave,
            time_seconds=current_time,
            overlay_type_name=getattr(cur_type, "name", ""),
            overlay_colors=colors,
            overlay_action=self._action_on,
        )
        self._preview.set_buffer(buffer)

    def _playhead_time(self, *, clamp: bool) -> float:
        slave = self._active_slave
        if slave is None:
            return 0.0
        try:
            raw = float(slave.wave._renderer.selectedLine.value())
        except Exception:
            raw = 0.0
        if clamp:
            raw = max(0.0, raw)
            dur = 0.0
            try:
                dur = float(getattr(slave.wave._renderer, "duration", 0.0) or 0.0)
            except (TypeError, ValueError):
                dur = 0.0
            if dur > 0.0 and raw > dur:
                raw = dur
        return raw

    def _on_place_tag_clicked(self) -> None:
        cur_type = self._current_type()
        slave = self._active_slave
        project_window = self._project_window
        if cur_type is None or slave is None or project_window is None:
            return
        commands = getattr(project_window, "commands", None)
        state = getattr(project_window, "state", None)
        master_id = getattr(slave, "_master_id", None)
        slave_id = getattr(slave, "boxID", None)
        if commands is None or state is None or master_id is None or slave_id is None:
            return
        try:
            state.master(master_id).slaves[slave_id].tag_types[
                getattr(cur_type, "name", "")
            ]
        except KeyError:
            return
        time_val = self._playhead_time(clamp=True)
        topology = list(getattr(cur_type, "topology", []) or [])
        if self._action_on:
            colors = [list(c) for c in self._colors]
            if len(colors) != len(topology):
                # Topology grew or shrank underneath us; normalise.
                colors = [[255, 255, 255] for _ in topology]
        else:
            colors = _pattern_service.solid_fill(len(topology), [0, 0, 0])
        tag = DomainTag(
            time_seconds=float(time_val),
            action=bool(self._action_on),
            colors=colors,
        )
        commands.push(
            AddOrReplaceTagCommand(
                master_id=str(master_id),
                slave_id=str(slave_id),
                type_name=str(getattr(cur_type, "name", "")),
                tag=tag,
            )
        )
        self._refresh_preview()

    # ---- Testing accessors --------------------------------------------------

    def active_slave(self) -> Optional[Any]:
        return self._active_slave

    def state_bar(self) -> QComboBox:
        return self._state_bar

    def place_button(self) -> QPushButton:
        return self._place_btn

    def edit_colors_button(self) -> QPushButton:
        return self._edit_colors_btn
