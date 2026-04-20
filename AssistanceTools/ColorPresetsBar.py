"""Horizontal bar of color-swatch buttons (global palette, in-memory).

Left click on a swatch selects it; right click removes it. The "+"
button requests that the host dialog capture the current picker color.
The widget owns no persistence — the host wires up save/load via the
presetsChanged signal.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QWidget

from AssistanceTools.FlowLayout import FlowLayout


class ColorSwatchButton(QPushButton):
    """Flat filled square. Left click selects; right click removes."""

    removeRequested = pyqtSignal()

    def __init__(self, rgb, parent=None):
        super().__init__(parent)
        self.rgb = [int(rgb[0]), int(rgb[1]), int(rgb[2])]
        self.setFixedSize(20, 20)
        self.setStyleSheet(
            "QPushButton { "
            f"background-color: rgb({self.rgb[0]}, {self.rgb[1]}, {self.rgb[2]}); "
            "border: 1px solid #333; "
            "}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.removeRequested.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class ColorPresetsBar(QWidget):
    """Flow layout of color swatches plus a trailing "+" button.

    Signals are in-memory only; persistence is the host's responsibility.
    """

    presetChosen = pyqtSignal(list)
    presetsChanged = pyqtSignal(list)
    addCurrentRequested = pyqtSignal()

    def __init__(self, presets=None, parent=None):
        super().__init__(parent)
        self._presets = [[int(c[0]), int(c[1]), int(c[2])] for c in (presets or [])]
        self._layout = FlowLayout(self)
        self._rebuild()

    def set_presets(self, presets):
        self._presets = [[int(c[0]), int(c[1]), int(c[2])] for c in (presets or [])]
        self._rebuild()

    def add_preset(self, rgb):
        normalized = [
            max(0, min(255, int(rgb[0]))),
            max(0, min(255, int(rgb[1]))),
            max(0, min(255, int(rgb[2]))),
        ]
        self._presets.append(normalized)
        self._rebuild()
        self.presetsChanged.emit([list(p) for p in self._presets])

    def remove_preset(self, index):
        if not (0 <= index < len(self._presets)):
            return
        self._presets.pop(index)
        self._rebuild()
        self.presetsChanged.emit([list(p) for p in self._presets])

    def _rebuild(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        for index, rgb in enumerate(self._presets):
            swatch = ColorSwatchButton(rgb, parent=self)
            swatch.clicked.connect(
                lambda _checked=False, c=list(rgb): self.presetChosen.emit(
                    list(c),
                )
            )
            swatch.removeRequested.connect(
                lambda i=index: self.remove_preset(i),
            )
            self._layout.addWidget(swatch)

        addButton = QPushButton("+", parent=self)
        addButton.setFixedSize(20, 20)
        addButton.clicked.connect(
            lambda _checked=False: self.addCurrentRequested.emit(),
        )
        self._layout.addWidget(addButton)
