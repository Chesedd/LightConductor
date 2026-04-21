"""Non-modal singleton popout that owns the entire Tag-editing UX:
state dropdown, per-LED color grid, preview, and Place tag. Replaces
the Phase 10 ``TagEditorWindow`` shell (which only embedded a state
combo + opened this dialog as a modal sub-dialog).

The window follows ``ProjectWindow.activeSlaveChanged`` and the active
slave's ``wave.manager.currentTypeChanged``; on either, the per-LED
grid is torn down and rebuilt from the new topology. Place tag pushes
an ``AddOrReplaceTagCommand`` so a second click at the same playhead
atomically replaces the prior tag of the same TagType.

Drag-paint state machine from Phase 9.2 is preserved verbatim: tests
construct the dialog with ``project_window=None`` plus explicit
``topology`` / ``slave_grid_columns`` / ``current_colors`` kwargs to
exercise drag without any project-window wiring.
"""

from __future__ import annotations

from typing import Any, List, Optional

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from AssistanceTools.ColorPicker import ColorPicker
from lightconductor.application.commands import AddOrReplaceTagCommand
from lightconductor.application.grid_sizing import compute_cell_size
from lightconductor.application.pattern_service import PatternService
from lightconductor.application.topology_bbox import compute_topology_bbox
from lightconductor.domain.models import Tag as DomainTag
from ProjectScreen.TagLogic.LedGridView import LedGridView
from ProjectScreen.TagLogic.TagScreen import ColorButton

_pattern_service = PatternService()


class TagPinsDialog(QDialog):
    """Non-modal Tag editor popout. Construct with ``project_window``
    to follow the project's active slave / current TagType. Construct
    with ``project_window=None`` plus topology kwargs to obtain a
    degenerate dialog suitable for drag-paint tests."""

    def __init__(
        self,
        project_window: Any = None,
        parent: Any = None,
        *,
        topology: Optional[List[int]] = None,
        slave_grid_columns: Optional[int] = None,
        current_colors: Optional[List[List[int]]] = None,
        led_cells: Optional[Any] = None,
        settings: Any = None,
        on_presets_changed: Any = None,
    ) -> None:
        super().__init__(parent if parent is not None else project_window)
        self._project_window = project_window
        self._active_slave: Any = None
        self._connected_manager: Any = None
        self._action_on: bool = True

        self._settings = settings
        self._on_presets_changed = on_presets_changed

        self._topology: List[int] = []
        self._slave_cols: int = 1
        self._led_cells: Optional[frozenset[int]] = None
        self._min_row: int = 0
        self._min_col: int = 0
        self._bbox_rows: int = 0
        self._bbox_cols: int = 0
        self._bbox_to_topo_pos: List[int] = []
        self.colors: List[List[int]] = []

        self._cell_buttons: List[ColorButton] = []
        self._buttons_by_pos: dict[int, ColorButton] = {}
        self._button_group: Optional[QButtonGroup] = None
        self._grid_container: Optional[QWidget] = None

        self._drag_active: bool = False
        self._drag_mode: Optional[str] = None
        self._drag_visited: set[int] = set()
        self._drag_color: List[int] = [0, 0, 0]

        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("Tag editor")

        self._build_ui()

        if project_window is not None:
            signal = getattr(project_window, "activeSlaveChanged", None)
            if signal is not None:
                signal.connect(self._on_active_slave_changed)
            if self._settings is None:
                self._settings = getattr(project_window, "settings", None)
            if self._on_presets_changed is None:
                self._on_presets_changed = getattr(
                    project_window,
                    "update_color_presets",
                    None,
                )
            self._build_presets_bar()
            self._apply_active_slave(getattr(project_window, "_active_slave", None))
        else:
            self._build_presets_bar()
            if topology is not None:
                self._install_topology(
                    topology=topology,
                    slave_grid_columns=int(slave_grid_columns or 1),
                    led_cells=led_cells,
                    current_colors=current_colors,
                )

    # ---- UI construction ---------------------------------------------------

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

        body = QHBoxLayout()

        left_col = QVBoxLayout()
        self._color_picker = ColorPicker()
        left_col.addWidget(self._color_picker)

        btn_row = QHBoxLayout()
        set_btn = QPushButton("Set color")
        set_btn.clicked.connect(self._on_set_color)
        fill_btn = QPushButton("Fill active LEDs")
        fill_btn.clicked.connect(self._on_fill_active)
        drop_btn = QPushButton("Drop color")
        drop_btn.clicked.connect(self._on_drop_color)
        btn_row.addWidget(set_btn)
        btn_row.addWidget(fill_btn)
        btn_row.addWidget(drop_btn)
        btn_row_widget = QWidget()
        btn_row_widget.setLayout(btn_row)
        left_col.addWidget(btn_row_widget)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("Range from"))
        self._range_from = QLineEdit("0")
        self._range_from.setFixedWidth(50)
        range_row.addWidget(self._range_from)
        range_row.addWidget(QLabel("to"))
        self._range_to = QLineEdit("0")
        self._range_to.setFixedWidth(50)
        range_row.addWidget(self._range_to)
        range_fill_btn = QPushButton("Fill range")
        range_fill_btn.clicked.connect(self._on_fill_range)
        range_row.addWidget(range_fill_btn)
        range_widget = QWidget()
        range_widget.setLayout(range_row)
        left_col.addWidget(range_widget)

        self._presets_bar = None
        self._presets_slot = QVBoxLayout()
        self._presets_slot.setContentsMargins(0, 0, 0, 0)
        presets_holder = QWidget()
        presets_holder.setLayout(self._presets_slot)
        left_col.addWidget(presets_holder)

        left_widget = QWidget()
        left_widget.setLayout(left_col)
        body.addWidget(left_widget)

        self._grid_container = QWidget()
        grid_outer = QVBoxLayout(self._grid_container)
        grid_outer.setContentsMargins(0, 0, 0, 0)
        grid_outer.setSpacing(0)
        body.addWidget(self._grid_container)

        body_widget = QWidget()
        body_widget.setLayout(body)
        root.addWidget(body_widget)

        self._hint_label = QLabel("")
        self._hint_label.setStyleSheet("color: #888;")
        root.addWidget(self._hint_label)

        self._place_btn = QPushButton("Place tag")
        self._place_btn.clicked.connect(self._on_place_tag_clicked)
        root.addWidget(self._place_btn)

        self._place_btn.setEnabled(False)
        self._set_color_controls_enabled(False)

        initial_w = 520
        initial_h = 480
        self.resize(initial_w, initial_h)

    def _build_presets_bar(self) -> None:
        if self._presets_bar is not None or self._settings is None:
            return
        from AssistanceTools.ColorPresetsBar import ColorPresetsBar

        presets = [list(p) for p in (self._settings.color_presets or [])]
        self._presets_bar = ColorPresetsBar(presets=presets)
        self._presets_bar.presetChosen.connect(self._on_preset_chosen)
        self._presets_bar.addCurrentRequested.connect(self._on_add_current_preset)
        self._presets_bar.presetsChanged.connect(self._on_presets_changed_internal)
        self._presets_slot.addWidget(self._presets_bar)

    # ---- Topology / per-LED grid ------------------------------------------

    def _install_topology(
        self,
        *,
        topology: List[int],
        slave_grid_columns: int,
        led_cells: Optional[Any],
        current_colors: Optional[List[List[int]]],
    ) -> None:
        self._topology = list(topology)
        self._slave_cols = max(1, int(slave_grid_columns))
        self._led_cells = frozenset(int(c) for c in led_cells) if led_cells else None

        if self._topology:
            self._min_row, self._min_col, max_row, max_col = compute_topology_bbox(
                self._topology,
                self._slave_cols,
            )
            self._bbox_rows = max_row - self._min_row + 1
            self._bbox_cols = max_col - self._min_col + 1
        else:
            self._min_row = 0
            self._min_col = 0
            self._bbox_rows = 0
            self._bbox_cols = 0

        default = [255, 255, 255]
        if current_colors and len(current_colors) == len(self._topology):
            self.colors = [list(c) for c in current_colors]
        else:
            self.colors = [list(default) for _ in self._topology]

        self._bbox_to_topo_pos = [-1] * (self._bbox_rows * self._bbox_cols)
        for pos, cell in enumerate(self._topology):
            r = cell // self._slave_cols - self._min_row
            c = cell % self._slave_cols - self._min_col
            bbox_idx = r * self._bbox_cols + c
            self._bbox_to_topo_pos[bbox_idx] = pos

        self._range_to.setText(str(max(0, len(self._topology) - 1)))
        self._rebuild_grid_widgets()
        self._set_color_controls_enabled(self._action_on and bool(self._topology))
        self._refresh_preview()

    def _clear_grid(self) -> None:
        self._cell_buttons = []
        self._buttons_by_pos = {}
        self._button_group = None
        if self._grid_container is None:
            return
        layout = self._grid_container.layout()
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _rebuild_grid_widgets(self) -> None:
        self._clear_grid()
        if self._grid_container is None or not self._topology:
            return
        layout = self._grid_container.layout()
        assert layout is not None
        self._button_group = QButtonGroup(self._grid_container)
        self._button_group.setExclusive(True)
        for r in range(self._bbox_rows):
            row_w = QWidget()
            row_layout = QHBoxLayout(row_w)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(0)
            for c in range(self._bbox_cols):
                bbox_idx = r * self._bbox_cols + c
                pos = self._bbox_to_topo_pos[bbox_idx]
                btn = ColorButton()
                btn.setCheckable(True)
                if pos == -1:
                    cell_idx = (self._min_row + r) * self._slave_cols + (
                        self._min_col + c
                    )
                    is_no_led = (
                        self._led_cells is not None and cell_idx not in self._led_cells
                    )
                    btn.setEnabled(False)
                    if is_no_led:
                        btn.setText("—")
                        btn.setStyleSheet(
                            "QPushButton { background-color: #ffffff; color: #333333;}"
                        )
                    else:
                        btn.setText("·")
                        btn.setStyleSheet(
                            "QPushButton { background-color: #4a2020; color: #888;}"
                        )
                else:
                    btn.setColor(self.colors[pos])
                    self._button_group.addButton(btn)
                    self._buttons_by_pos[pos] = btn
                    btn.installEventFilter(self)
                self._cell_buttons.append(btn)
                row_layout.addWidget(btn)
            layout.addWidget(row_w)
        self._apply_cell_size()

    # ---- Active slave / current type wiring -------------------------------

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
        slave = self._active_slave
        slave_name = getattr(slave, "title", "") or ""
        if cur_type is None:
            self._topology = []
            self.colors = []
            self._clear_grid()
            self._place_btn.setEnabled(False)
            self._set_color_controls_enabled(False)
            self._hint_label.setText(
                "No active slave" if slave is None else "No tag type selected"
            )
            self._preview.set_buffer([])
            self.setWindowTitle(
                f"Tag editor — {slave_name}" if slave_name else "Tag editor"
            )
            return
        topology = list(getattr(cur_type, "topology", []) or [])
        slave_cols = int(getattr(slave, "_grid_columns", 0) or 0) if slave else 0
        if slave_cols < 1:
            slave_cols = max(1, int(getattr(cur_type, "table", 1) or 1))
        led_cells_attr = (
            getattr(slave, "_led_cells", None) if slave is not None else None
        )
        self._install_topology(
            topology=topology,
            slave_grid_columns=slave_cols,
            led_cells=led_cells_attr,
            current_colors=None,
        )
        self._hint_label.setText("")
        self._place_btn.setEnabled(bool(topology))
        type_name = getattr(cur_type, "name", "") or ""
        if slave_name and type_name:
            self.setWindowTitle(f"Tag editor — {slave_name} / {type_name}")
        elif type_name:
            self.setWindowTitle(f"Tag editor — {type_name}")
        else:
            self.setWindowTitle("Tag editor")

    # ---- State combo ------------------------------------------------------

    def _on_state_changed(self, state: str) -> None:
        self._action_on = state == "On"
        self._set_color_controls_enabled(self._action_on and bool(self._topology))
        self._refresh_preview()

    def _set_color_controls_enabled(self, enabled: bool) -> None:
        if self._grid_container is not None:
            self._grid_container.setEnabled(enabled)

    # ---- Preview ----------------------------------------------------------

    def _refresh_preview(self) -> None:
        cur_type = self._current_type()
        if cur_type is not None and self._project_window is not None:
            from lightconductor.application.led_preview import (
                render_canvas_with_overlay,
            )

            slave = self._domain_slave()
            if slave is None:
                self._preview.set_buffer([])
                return
            if self._action_on:
                colors = [list(c) for c in self.colors]
            else:
                colors = [[0, 0, 0] for _ in self.colors]
            buffer = render_canvas_with_overlay(
                slave=slave,
                time_seconds=self._playhead_time(clamp=True),
                overlay_type_name=getattr(cur_type, "name", ""),
                overlay_colors=colors,
                overlay_action=self._action_on,
            )
            self._preview.set_buffer(buffer)
            return

        if not self._topology or self._bbox_rows <= 0 or self._bbox_cols <= 0:
            self._preview.set_buffer([])
            return
        buf: List[tuple[int, int, int]] = [(0, 0, 0)] * (
            self._bbox_rows * self._bbox_cols
        )
        for pos, cell in enumerate(self._topology):
            r = cell // self._slave_cols - self._min_row
            c = cell % self._slave_cols - self._min_col
            bbox_idx = r * self._bbox_cols + c
            rgb = self.colors[pos] if self._action_on else [0, 0, 0]
            buf[bbox_idx] = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        self._preview.set_buffer(buf)

    # ---- Place tag --------------------------------------------------------

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
        type_name = getattr(cur_type, "name", "") or ""
        try:
            state.master(master_id).slaves[slave_id].tag_types[type_name]
        except KeyError:
            return
        time_val = self._playhead_time(clamp=True)
        topology = list(getattr(cur_type, "topology", []) or [])
        if self._action_on:
            colors = [list(c) for c in self.colors]
            if len(colors) != len(topology):
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
                type_name=str(type_name),
                tag=tag,
            )
        )
        self._refresh_preview()

    # ---- Cell sizing & color editing --------------------------------------

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_cell_size()

    def _apply_cell_size(self) -> None:
        if not self._cell_buttons or self._grid_container is None:
            return
        w = self._grid_container.width()
        h = self._grid_container.height()
        side = compute_cell_size(
            w,
            h,
            self._bbox_rows,
            self._bbox_cols,
            min_size=6,
        )
        for btn in self._cell_buttons:
            btn.setFixedSize(side, side)

    def _on_set_color(self) -> None:
        if self._button_group is None:
            return
        btn = self._button_group.checkedButton()
        if btn is None:
            return
        rgb = list(self._color_picker.rgb)
        btn.setColor(rgb)
        pos = self._pos_of_button(btn)
        if pos is not None:
            self.colors[pos] = list(rgb)
            self._refresh_preview()

    def _on_fill_active(self) -> None:
        rgb = list(self._color_picker.rgb)
        for pos, btn in self._buttons_by_pos.items():
            btn.setColor(rgb)
            self.colors[pos] = list(rgb)
        self._refresh_preview()

    def _on_drop_color(self) -> None:
        if self._button_group is None:
            return
        btn = self._button_group.checkedButton()
        if btn is None:
            return
        rgb = [0, 0, 0]
        btn.setColor(rgb)
        pos = self._pos_of_button(btn)
        if pos is not None:
            self.colors[pos] = list(rgb)
            self._refresh_preview()

    def _on_fill_range(self) -> None:
        try:
            lo = max(0, int(self._range_from.text()))
        except ValueError:
            return
        try:
            hi = min(len(self._topology) - 1, int(self._range_to.text()))
        except ValueError:
            return
        if lo > hi:
            return
        rgb = list(self._color_picker.rgb)
        for pos in range(lo, hi + 1):
            btn = self._buttons_by_pos.get(pos)
            if btn is not None:
                btn.setColor(rgb)
                self.colors[pos] = list(rgb)
        self._refresh_preview()

    def _pos_of_button(self, btn: Any) -> Optional[int]:
        for pos, b in self._buttons_by_pos.items():
            if b is btn:
                return pos
        return None

    def _on_preset_chosen(self, rgb: Any) -> None:
        self._color_picker.setColor(list(rgb))

    def _on_add_current_preset(self) -> None:
        if self._presets_bar is None:
            return
        self._presets_bar.add_preset(list(self._color_picker.rgb))

    def _on_presets_changed_internal(self, presets: Any) -> None:
        if self._on_presets_changed is not None:
            self._on_presets_changed([list(p) for p in presets])

    # ---- Drag-paint (preserved from Phase 9.2) ----------------------------

    def _drag_begin(self, pos: int, button: str) -> None:
        """Start a drag. Left button paints with the current color
        picker value; right button clears to [0, 0, 0]."""
        self._drag_active = True
        self._drag_mode = "PAINT" if button == "left" else "CLEAR"
        self._drag_visited = set()
        if self._drag_mode == "PAINT":
            self._drag_color = list(self._color_picker.rgb)
        else:
            self._drag_color = [0, 0, 0]
        self._drag_apply(pos)

    def _drag_apply(self, pos: int) -> None:
        if not self._drag_active or self._drag_mode is None:
            return
        if pos in self._drag_visited:
            return
        self._drag_visited.add(pos)
        btn = self._buttons_by_pos.get(pos)
        if btn is None:
            return
        btn.setColor(list(self._drag_color))
        self.colors[pos] = list(self._drag_color)
        self._refresh_preview()

    def _drag_end(self) -> None:
        self._drag_active = False
        self._drag_mode = None
        self._drag_visited = set()

    def _pos_at_global(self, global_pos: Any) -> Optional[int]:
        w = QApplication.widgetAt(global_pos)
        for pos, btn in self._buttons_by_pos.items():
            if btn is w:
                return pos
        return None

    def eventFilter(self, obj, event):  # type: ignore[override]
        et = event.type()
        if et == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            btn_id = event.button()
            if btn_id not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
                return super().eventFilter(obj, event)
            for pos, b in self._buttons_by_pos.items():
                if b is obj:
                    which = "left" if btn_id == Qt.MouseButton.LeftButton else "right"
                    self._drag_begin(pos, which)
                    return btn_id == Qt.MouseButton.RightButton
        elif (
            et == QEvent.Type.MouseMove
            and isinstance(event, QMouseEvent)
            and self._drag_active
        ):
            pos = self._pos_at_global(event.globalPosition().toPoint())
            if pos is not None:
                self._drag_apply(pos)
            return False
        elif (
            et == QEvent.Type.MouseButtonRelease
            and isinstance(event, QMouseEvent)
            and self._drag_active
            and event.button()
            in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton)
        ):
            self._drag_end()
            return False
        return super().eventFilter(obj, event)

    # ---- Testing accessors ------------------------------------------------

    def active_slave(self) -> Optional[Any]:
        return self._active_slave

    def state_bar(self) -> QComboBox:
        return self._state_bar

    def place_button(self) -> QPushButton:
        return self._place_btn
