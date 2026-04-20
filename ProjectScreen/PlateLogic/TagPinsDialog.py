from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from AssistanceTools.ColorPicker import ColorPicker
from lightconductor.application.topology_bbox import compute_topology_bbox
from ProjectScreen.TagLogic.TagScreen import ColorButton


class TagPinsDialog(QDialog):
    colorsChanged = pyqtSignal(list)

    def __init__(
        self,
        topology,
        slave_grid_columns,
        current_colors,
        led_cells=None,
        settings=None,
        on_presets_changed=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit per-LED colors")
        self.setModal(True)
        self._topology = list(topology)
        self._slave_cols = int(slave_grid_columns)
        self._led_cells = frozenset(led_cells) if led_cells is not None else None
        self._settings = settings
        self._on_presets_changed = on_presets_changed

        self._min_row, self._min_col, max_row, max_col = compute_topology_bbox(
            self._topology,
            self._slave_cols,
        )
        self._bbox_rows = max_row - self._min_row + 1
        self._bbox_cols = max_col - self._min_col + 1

        default = [255, 255, 255]
        if len(current_colors) == len(self._topology):
            self.colors = [list(c) for c in current_colors]
        else:
            self.colors = [list(default) for _ in self._topology]

        self._bbox_to_topo_pos = [-1] * (self._bbox_rows * self._bbox_cols)
        for pos, cell in enumerate(self._topology):
            r = cell // self._slave_cols - self._min_row
            c = cell % self._slave_cols - self._min_col
            bbox_idx = r * self._bbox_cols + c
            self._bbox_to_topo_pos[bbox_idx] = pos

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        from ProjectScreen.TagLogic.LedGridView import LedGridView

        self._preview = LedGridView(
            state=None,
            master_id=None,
            slave_id=None,
            parent=self,
        )
        root.addWidget(self._preview)

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
        self._range_to = QLineEdit(str(max(0, len(self._topology) - 1)))
        self._range_to.setFixedWidth(50)
        range_row.addWidget(self._range_to)
        range_fill_btn = QPushButton("Fill range")
        range_fill_btn.clicked.connect(self._on_fill_range)
        range_row.addWidget(range_fill_btn)
        range_widget = QWidget()
        range_widget.setLayout(range_row)
        left_col.addWidget(range_widget)

        self._presets_bar = None
        if self._settings is not None:
            from AssistanceTools.ColorPresetsBar import ColorPresetsBar

            presets = [list(p) for p in (self._settings.color_presets or [])]
            self._presets_bar = ColorPresetsBar(presets=presets)
            self._presets_bar.presetChosen.connect(self._on_preset_chosen)
            self._presets_bar.addCurrentRequested.connect(
                self._on_add_current_preset,
            )
            self._presets_bar.presetsChanged.connect(
                self._on_presets_changed_internal,
            )
            left_col.addWidget(self._presets_bar)

        left_widget = QWidget()
        left_widget.setLayout(left_col)
        body.addWidget(left_widget)

        right_col = QVBoxLayout()
        self._button_group = QButtonGroup()
        self._button_group.setExclusive(True)
        self._buttons_by_pos = {}
        for r in range(self._bbox_rows):
            row_w = QWidget()
            row_layout = QHBoxLayout(row_w)
            for c in range(self._bbox_cols):
                bbox_idx = r * self._bbox_cols + c
                pos = self._bbox_to_topo_pos[bbox_idx]
                btn = ColorButton()
                btn.setFixedSize(20, 20)
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
                row_layout.addWidget(btn)
            right_col.addWidget(row_w)

        right_widget = QWidget()
        right_widget.setLayout(right_col)
        body.addWidget(right_widget)

        body_widget = QWidget()
        body_widget.setLayout(body)
        root.addWidget(body_widget)

        btns = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        btns_widget = QWidget()
        btns_widget.setLayout(btns)
        root.addWidget(btns_widget)

        self._refresh_preview()

    def _on_set_color(self):
        btn = self._button_group.checkedButton()
        if btn is None:
            return
        rgb = list(self._color_picker.rgb)
        btn.setColor(rgb)
        pos = self._pos_of_button(btn)
        if pos is not None:
            self.colors[pos] = list(rgb)
            self._refresh_preview()

    def _on_fill_active(self):
        rgb = list(self._color_picker.rgb)
        for pos, btn in self._buttons_by_pos.items():
            btn.setColor(rgb)
            self.colors[pos] = list(rgb)
        self._refresh_preview()

    def _on_drop_color(self):
        btn = self._button_group.checkedButton()
        if btn is None:
            return
        rgb = [0, 0, 0]
        btn.setColor(rgb)
        pos = self._pos_of_button(btn)
        if pos is not None:
            self.colors[pos] = list(rgb)
            self._refresh_preview()

    def _on_fill_range(self):
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

    def _pos_of_button(self, btn):
        for pos, b in self._buttons_by_pos.items():
            if b is btn:
                return pos
        return None

    def _refresh_preview(self):
        buf = [(0, 0, 0)] * (self._bbox_rows * self._bbox_cols)
        for pos, cell in enumerate(self._topology):
            r = cell // self._slave_cols - self._min_row
            c = cell % self._slave_cols - self._min_col
            bbox_idx = r * self._bbox_cols + c
            rgb = self.colors[pos]
            buf[bbox_idx] = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        self._preview.set_buffer(buf)

    def _on_preset_chosen(self, rgb):
        self._color_picker.setColor(list(rgb))

    def _on_add_current_preset(self):
        if self._presets_bar is None:
            return
        self._presets_bar.add_preset(list(self._color_picker.rgb))

    def _on_presets_changed_internal(self, presets):
        if self._on_presets_changed is not None:
            self._on_presets_changed([list(p) for p in presets])

    def _on_ok(self):
        self.colorsChanged.emit(list(self.colors))
        self.accept()
