from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from lightconductor.application.grid_sizing import compute_cell_size
from lightconductor.application.led_preview import (
    _safe_int,
    render_canvas_at,
)
from lightconductor.application.project_state import (
    SlaveAdded,
    SlaveRemoved,
    StateReplaced,
    TagAdded,
    TagRemoved,
    TagTypeAdded,
    TagTypeRemoved,
    TagTypeUpdated,
    TagUpdated,
)

MIN_CELL_PX = 6
TARGET_CELL_PX_2D = 10
STRIP_ROW_HEIGHT_PX = 28
BORDER_PX = 1


class LedGridView(QWidget):
    def __init__(
        self,
        state=None,
        master_id=None,
        slave_id=None,
        parent=None,
        resizable=False,
    ):
        super().__init__(parent)
        self._state = state
        self._master_id = master_id
        self._slave_id = slave_id
        self._current_time = 0.0
        self._buffer = []
        self._strip_mode = True
        self._resizable = bool(resizable)

        self.setFixedHeight(STRIP_ROW_HEIGHT_PX)
        self.setMinimumWidth(100)

        self._unsubscribe = None
        if self._state is not None:
            self._unsubscribe = self._state.subscribe(
                self._on_state_event,
            )
            # Qt will call the lambda after C++ destruction; the
            # lambda only touches the unsubscribe callable, never
            # self, so it is safe regardless of Python-side state.
            self.destroyed.connect(
                lambda _=None, u=self._unsubscribe: u(),
            )

        self._recompute()

    def set_time(self, time_seconds):
        self._current_time = max(0.0, float(time_seconds))
        self._recompute()

    def set_buffer(self, buffer):
        """Preview path: caller supplies a precomputed RGB buffer
        (list of (r,g,b) tuples). Bypasses _recompute and state
        resolution. Triggers repaint."""
        self._buffer = list(buffer or [])
        self.update()

    def _resolve_slave(self):
        try:
            if self._state is None or self._master_id is None or self._slave_id is None:
                return None
            return self._state.master(self._master_id).slaves[self._slave_id]
        except KeyError:
            return None

    def _apply_sizing_from_slave(self, slave):
        """Update height based on slave grid. Called from _recompute
        after _resolve_slave. Strip-mode keeps a 28px legacy fixed
        height. Grid-mode: when ``resizable`` is True the widget is
        allowed to expand vertically so the caller (e.g. the popout
        window) can scale cells via ``compute_cell_size``; otherwise
        the legacy fixed-height layout is preserved for embedded
        dialogs."""
        if slave is None:
            self._strip_mode = True
            self.setFixedHeight(STRIP_ROW_HEIGHT_PX)
            return
        rows = int(getattr(slave, "grid_rows", 1) or 1)
        if rows <= 1:
            self._strip_mode = True
            self.setFixedHeight(STRIP_ROW_HEIGHT_PX)
        else:
            self._strip_mode = False
            if self._resizable:
                self.setMinimumHeight(
                    rows * MIN_CELL_PX + 2 * BORDER_PX,
                )
                self.setMaximumHeight(16777215)
                self.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Expanding,
                )
            else:
                self.setFixedHeight(
                    rows * TARGET_CELL_PX_2D + 2 * BORDER_PX,
                )

    def _recompute(self):
        slave = self._resolve_slave()
        self._apply_sizing_from_slave(slave)
        if slave is None or _safe_int(getattr(slave, "led_count", 0)) <= 0:
            self._buffer = []
        else:
            self._buffer = render_canvas_at(
                slave,
                self._current_time,
            )
        self.update()

    def _on_state_event(self, event):
        if isinstance(event, StateReplaced):
            self._recompute()
            return
        if getattr(event, "master_id", None) != self._master_id:
            return
        if getattr(event, "slave_id", None) != self._slave_id:
            return
        if isinstance(
            event,
            (
                TagAdded,
                TagRemoved,
                TagUpdated,
                TagTypeAdded,
                TagTypeRemoved,
                TagTypeUpdated,
                SlaveAdded,
                SlaveRemoved,
            ),
        ):
            self._recompute()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Ensure repaint so compute_cell_size re-runs against the new
        # available area. Qt schedules a paintEvent automatically on
        # resize, but the explicit update() mirrors the 9.1 pattern
        # and guards against subclass-layering surprises.
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            width = self.width()
            height = self.height()
            painter.fillRect(self.rect(), QColor("#1a1a1a"))

            pen = QPen(QColor("#444"))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            border = QRectF(self.rect()).adjusted(
                0.5,
                0.5,
                -0.5,
                -0.5,
            )
            painter.drawRect(border)

            if not self._buffer:
                return

            slave = self._resolve_slave()
            rows = 1
            cols = len(self._buffer)
            if slave is not None:
                rows = max(1, int(getattr(slave, "grid_rows", 1) or 1))
                cols = max(1, int(getattr(slave, "grid_columns", 0) or 0))
            total_cells = min(len(self._buffer), rows * cols)

            inside_w = max(0, width - 2 * BORDER_PX)
            inside_h = max(0, height - 2 * BORDER_PX)

            if self._strip_mode:
                cell_w = inside_w / max(1, cols)
                cell_h = inside_h
                painter.setPen(Qt.PenStyle.NoPen)
                for i in range(total_cells):
                    (r, g, b) = self._buffer[i]
                    color = (
                        QColor("#2a2a2a") if (r, g, b) == (0, 0, 0) else QColor(r, g, b)
                    )
                    x = BORDER_PX + i * cell_w
                    rect = QRectF(
                        x,
                        float(BORDER_PX),
                        max(1.0, cell_w - 0.5),
                        float(cell_h),
                    )
                    painter.fillRect(rect, QBrush(color))
            else:
                cell_size = float(
                    compute_cell_size(
                        int(inside_w),
                        int(inside_h),
                        int(rows),
                        int(cols),
                        min_size=MIN_CELL_PX,
                    ),
                )
                cell_pen = QPen(QColor("#0d0d0d"))
                cell_pen.setWidth(1)
                for idx in range(total_cells):
                    r_idx = idx // cols
                    c_idx = idx % cols
                    (r, g, b) = self._buffer[idx]
                    color = (
                        QColor("#2a2a2a") if (r, g, b) == (0, 0, 0) else QColor(r, g, b)
                    )
                    x = BORDER_PX + c_idx * cell_size
                    y = BORDER_PX + r_idx * cell_size
                    rect = QRectF(
                        x,
                        y,
                        cell_size,
                        cell_size,
                    )
                    painter.fillRect(rect, QBrush(color))
                    painter.setPen(cell_pen)
                    painter.drawRect(rect)
        finally:
            painter.end()
