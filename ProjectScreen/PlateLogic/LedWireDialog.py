from PyQt6.QtCore import QEvent, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from lightconductor.application.grid_sizing import compute_cell_size
from lightconductor.application.grid_zoom import (
    DEFAULT_MIN_CELL,
    apply_wheel_zoom,
)
from lightconductor.application.wire_assignment import (
    add_to_wire,
    remove_from_wire,
    validate_wire_assignment,
)


class LedWireDialog(QDialog):
    """Interactive editor for slave.led_cells (wire order of
    physical LEDs on the canvas).

    Grid shows canvas_rows x canvas_cols clickable cells. Click an
    empty cell to assign the next wire number. Click a numbered
    cell to remove it; remaining cells keep their relative order
    and wire indices remap automatically. OK enables when exactly
    led_count cells are placed.

    Mouse wheel over the grid zooms cells in/out. The first wheel
    tick pins the cell size to a manual value; subsequent dialog
    resizes no longer re-fit (``_user_zoomed``). A ``QScrollArea``
    wraps the grid so oversized content scrolls.
    """

    wireConfigured = pyqtSignal(list)

    def __init__(
        self,
        canvas_rows,
        canvas_cols,
        led_count,
        initial_cells=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Configure LED wire")
        self.setModal(True)
        self._canvas_rows = max(1, int(canvas_rows))
        self._canvas_cols = max(1, int(canvas_cols))
        self._led_count = max(0, int(led_count))

        canvas_size = self._canvas_rows * self._canvas_cols
        existing: list[int] = []
        seen: set[int] = set()
        for c in initial_cells or []:
            try:
                ci = int(c)
            except (TypeError, ValueError):
                continue
            if 0 <= ci < canvas_size and ci not in seen:
                existing.append(ci)
                seen.add(ci)
                if len(existing) >= self._led_count:
                    break
        self._order: list[int] = existing

        self._buttons: dict[int, QPushButton] = {}
        # Drag-paint state. mode is "WIRE_ADD" | "WIRE_REMOVE" | None.
        # _snapshot holds the pre-drag order so we can roll back on
        # validation failure.
        self._drag_active: bool = False
        self._drag_mode: str | None = None
        self._drag_visited: set[int] = set()
        self._drag_snapshot: list[int] = []
        self._suppress_next_click: bool = False
        # Zoom state. _cell_size is the pixel side of each square cell
        # button. _user_zoomed flips to True on the first wheel tick;
        # while True, resizeEvent stops re-fitting and the user's
        # manual size sticks.
        self._cell_size: int = 32
        self._user_zoomed: bool = False
        # Middle-button pan state. Active only while the middle
        # button is held. Orthogonal to left-button drag-paint.
        self._pan_active: bool = False
        self._pan_start_global: QPoint | None = None
        self._pan_scroll_start: tuple[int, int] = (0, 0)
        self._build_ui()
        self._sync_buttons()

    def _build_ui(self):
        root = QVBoxLayout(self)
        self._counter_label = QLabel("")
        root.addWidget(self._counter_label)

        self._grid_widget = QWidget()
        grid_layout = QVBoxLayout(self._grid_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(0)
        for r in range(self._canvas_rows):
            row_w = QWidget()
            row_layout = QHBoxLayout(row_w)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(0)
            for c in range(self._canvas_cols):
                index = r * self._canvas_cols + c
                btn = QPushButton("")
                btn.setCheckable(True)
                btn.clicked.connect(
                    lambda _checked=False, i=index: self._toggle_cell(i),
                )
                btn.installEventFilter(self)
                self._buttons[index] = btn
                row_layout.addWidget(btn)
            grid_layout.addWidget(row_w)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(False)
        self._scroll.setWidget(self._grid_widget)
        self._scroll.viewport().installEventFilter(self)
        root.addWidget(self._scroll)

        btn_row = QHBoxLayout()
        self._ok_btn = QPushButton("OK")
        self._ok_btn.clicked.connect(self._on_ok)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._ok_btn)
        btn_row.addWidget(self._cancel_btn)
        btn_row_w = QWidget()
        btn_row_w.setLayout(btn_row)
        root.addWidget(btn_row_w)

        # Reasonable initial dialog size; resizeEvent recomputes cells.
        initial_side = 32
        initial_w = max(260, self._canvas_cols * initial_side + 40)
        initial_h = max(200, self._canvas_rows * initial_side + 120)
        self.resize(initial_w, initial_h)
        self._fit_cell_size()
        self._apply_cell_size()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._user_zoomed:
            self._fit_cell_size()
        self._apply_cell_size()

    def _fit_cell_size(self) -> None:
        viewport = self._scroll.viewport()
        w = viewport.width()
        h = viewport.height()
        self._cell_size = compute_cell_size(
            w,
            h,
            self._canvas_rows,
            self._canvas_cols,
            min_size=DEFAULT_MIN_CELL,
        )

    def _apply_cell_size(self):
        if not self._buttons:
            return
        side = self._cell_size
        for btn in self._buttons.values():
            btn.setFixedSize(side, side)
        self._grid_widget.setFixedSize(
            self._canvas_cols * side,
            self._canvas_rows * side,
        )

    def _on_wheel_zoom(self, delta: int) -> None:
        if delta == 0:
            return
        self._user_zoomed = True
        self._cell_size = apply_wheel_zoom(self._cell_size, delta)
        self._apply_cell_size()

    def _toggle_cell(self, index):
        if self._suppress_next_click:
            self._suppress_next_click = False
            return
        if index in self._order:
            self._order = remove_from_wire(self._order, index)
        else:
            if len(self._order) >= self._led_count:
                return
            self._order = add_to_wire(self._order, index)
        self._sync_buttons()

    # --- Drag-paint -----------------------------------------------------

    def _drag_begin(self, index: int, shift: bool) -> None:
        """Start a drag. Shift-press removes cells from the wire;
        otherwise cells are assigned consecutive wire indices in the
        order the cursor visits them."""
        self._drag_active = True
        self._drag_mode = "WIRE_REMOVE" if shift else "WIRE_ADD"
        self._drag_visited = set()
        self._drag_snapshot = list(self._order)
        self._suppress_next_click = True
        self._drag_apply(index)

    def _drag_apply(self, index: int) -> None:
        if not self._drag_active or self._drag_mode is None:
            return
        if index in self._drag_visited:
            return
        self._drag_visited.add(index)
        if self._drag_mode == "WIRE_ADD":
            if index in self._order:
                return
            if len(self._order) >= self._led_count:
                return
            self._order = add_to_wire(self._order, index)
        else:  # WIRE_REMOVE
            if index not in self._order:
                return
            self._order = remove_from_wire(self._order, index)
        self._sync_buttons()

    def _drag_end(self) -> None:
        """Finalize drag. If the result fails validation, restore the
        pre-drag snapshot and show the same warning as OK-time invalid
        wire."""
        if not self._drag_active:
            return
        self._drag_active = False
        self._drag_mode = None
        self._drag_visited = set()
        canvas = self._canvas_rows * self._canvas_cols
        errors = validate_wire_assignment(
            self._order,
            canvas,
            len(self._order),
        )
        if errors:
            self._order = list(self._drag_snapshot)
            self._sync_buttons()
            QMessageBox.warning(
                self,
                "Invalid wire",
                "\n".join(errors),
            )
        self._drag_snapshot = []

    def _index_at_global(self, global_pos) -> int | None:
        w = QApplication.widgetAt(global_pos)
        for idx, btn in self._buttons.items():
            if btn is w:
                return idx
        return None

    def eventFilter(self, obj, event):  # type: ignore[override]
        et = event.type()
        if et == QEvent.Type.Wheel and obj is self._scroll.viewport():
            if isinstance(event, QWheelEvent):
                delta = event.angleDelta().y()
                if delta != 0:
                    self._on_wheel_zoom(delta)
                    event.accept()
                    return True
            return False
        if (
            et == QEvent.Type.MouseButtonPress
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.MiddleButton
        ):
            self._pan_begin(event.globalPosition().toPoint())
            return True
        if (
            et == QEvent.Type.MouseMove
            and isinstance(event, QMouseEvent)
            and self._pan_active
        ):
            self._pan_apply(event.globalPosition().toPoint())
            return True
        if (
            et == QEvent.Type.MouseButtonRelease
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.MiddleButton
            and self._pan_active
        ):
            self._pan_end()
            return True
        if (
            et == QEvent.Type.MouseButtonPress
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.LeftButton
        ):
            for idx, btn in self._buttons.items():
                if btn is obj:
                    shift = bool(
                        event.modifiers() & Qt.KeyboardModifier.ShiftModifier,
                    )
                    self._drag_begin(idx, shift)
                    return False
        elif (
            et == QEvent.Type.MouseMove
            and isinstance(event, QMouseEvent)
            and self._drag_active
        ):
            idx = self._index_at_global(event.globalPosition().toPoint())
            if idx is not None:
                self._drag_apply(idx)
            return False
        elif (
            et == QEvent.Type.MouseButtonRelease
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.LeftButton
            and self._drag_active
        ):
            self._drag_end()
            return False
        return super().eventFilter(obj, event)

    # --- Middle-button pan ---------------------------------------------

    def _pan_begin(self, global_pos: QPoint) -> None:
        self._pan_active = True
        self._pan_start_global = global_pos
        hbar = self._scroll.horizontalScrollBar()
        vbar = self._scroll.verticalScrollBar()
        self._pan_scroll_start = (hbar.value(), vbar.value())
        self._scroll.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def _pan_apply(self, global_pos: QPoint) -> None:
        if self._pan_start_global is None:
            return
        delta = global_pos - self._pan_start_global
        h0, v0 = self._pan_scroll_start
        self._scroll.horizontalScrollBar().setValue(h0 - delta.x())
        self._scroll.verticalScrollBar().setValue(v0 - delta.y())

    def _pan_end(self) -> None:
        self._pan_active = False
        self._pan_start_global = None
        self._scroll.viewport().unsetCursor()

    def _sync_buttons(self):
        for index, btn in self._buttons.items():
            if index in self._order:
                position = self._order.index(index)
                btn.setChecked(True)
                btn.setText(str(position))
            else:
                btn.setChecked(False)
                btn.setText("")
        self._counter_label.setText(f"Placed: {len(self._order)} / {self._led_count}")
        self._ok_btn.setEnabled(len(self._order) == self._led_count)

    def _on_ok(self):
        canvas = self._canvas_rows * self._canvas_cols
        errors = validate_wire_assignment(
            self._order,
            canvas,
            self._led_count,
        )
        if errors:
            QMessageBox.warning(
                self,
                "Invalid wire",
                "\n".join(errors),
            )
            return
        self.wireConfigured.emit(list(self._order))
        self.accept()

    @property
    def cells(self):
        return list(self._order)
