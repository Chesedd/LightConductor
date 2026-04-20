from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush
from PyQt6.QtWidgets import QWidget

from lightconductor.application.led_preview import (
    render_led_strip_at, _safe_int,
)


class LedStripView(QWidget):
    def __init__(self, state=None, master_id=None, slave_id=None, parent=None):
        super().__init__(parent)
        self._state = state
        self._master_id = master_id
        self._slave_id = slave_id
        self._current_time = 0.0
        self._buffer = []

        self.setFixedHeight(28)
        self.setMinimumWidth(100)

        self._recompute()

    def set_time(self, time_seconds):
        self._current_time = max(0.0, float(time_seconds))
        self._recompute()

    def _resolve_slave(self):
        try:
            if self._state is None or self._master_id is None or self._slave_id is None:
                return None
            return self._state.master(self._master_id).slaves[self._slave_id]
        except KeyError:
            return None

    def _recompute(self):
        slave = self._resolve_slave()
        if slave is None or _safe_int(getattr(slave, "led_count", 0)) <= 0:
            self._buffer = []
        else:
            self._buffer = render_led_strip_at(slave, self._current_time)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            width = self.width()
            height = self.height()

            painter.fillRect(self.rect(), QColor("#1a1a1a"))

            pen = QPen(QColor("#888"))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            border = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            painter.drawRect(border)

            if not self._buffer:
                return

            n = len(self._buffer)
            inside_w = max(0, width - 2)
            inside_h = max(0, height - 2)
            rect_w_f = inside_w / n if n > 0 else 0.0

            painter.setPen(Qt.PenStyle.NoPen)
            for i, (r, g, b) in enumerate(self._buffer):
                if (r, g, b) == (0, 0, 0):
                    color = QColor("#2a2a2a")
                else:
                    color = QColor(r, g, b)
                x = 1 + i * rect_w_f
                w = max(1.0, rect_w_f - 0.5)
                rect = QRectF(x, 1.0, w, float(inside_h))
                painter.fillRect(rect, QBrush(color))
        finally:
            painter.end()
