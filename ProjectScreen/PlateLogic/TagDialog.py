from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lightconductor.application.pattern_service import PatternService
from ProjectScreen.PlateLogic.TagPinsDialog import TagPinsDialog

_pattern_service = PatternService()


class TagDialog(QDialog):
    tagCreated = pyqtSignal(dict)

    def __init__(
        self,
        rows,
        columns,
        topology,
        parent=None,
        *,
        slave=None,
        type_name=None,
        current_time=0.0,
        led_count=0,
        settings=None,
        on_presets_changed=None,
        slave_grid_columns=0,
    ):
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
        self.topology = list(topology)
        self.colors = [[255, 255, 255] for _ in self.topology]
        self._preview_slave = slave
        self._preview_type_name = type_name
        self._preview_time = float(current_time or 0.0)
        self._preview_led_count = int(led_count or 0)
        self._settings = settings
        self._on_presets_changed = on_presets_changed
        self._slave_grid_columns = int(slave_grid_columns or 0)
        self.uiCreate()

    def uiCreate(self):
        self.params = QWidget()
        self.paramsLayer = QVBoxLayout(self.params)

        self.mainScreen = QWidget()
        self.mainLayout = QVBoxLayout(self.mainScreen)
        self.mainLayout.addWidget(self.initStateDropBox())
        self._edit_colors_btn = QPushButton("Edit per-LED colors...")
        self._edit_colors_btn.clicked.connect(self._open_pins_dialog)
        self.mainLayout.addWidget(self._edit_colors_btn)
        self.mainLayout.addWidget(self.params)
        self.mainLayout.addWidget(self.initButtons())

        self.ledPreview = None
        if (
            self._preview_slave is not None
            and self._preview_type_name is not None
            and self._preview_led_count > 0
        ):
            from ProjectScreen.TagLogic.LedGridView import LedGridView

            self.ledPreview = LedGridView(
                state=None,
                master_id=None,
                slave_id=None,
                parent=self,
            )

        top = QVBoxLayout(self)
        if self.ledPreview is not None:
            top.addWidget(self.ledPreview)
        top.addWidget(self.mainScreen)

        self.changeParams("On")
        self._refresh_preview()

    def initStateDropBox(self):
        stateText = QLabel("Состояние")
        self.stateBar = QComboBox()
        self.stateBar.addItems(["On", "Off"])
        self.stateBar.currentTextChanged.connect(self.changeParams)
        state = QWidget()
        stateLayout = QHBoxLayout(state)
        stateLayout.addWidget(stateText)
        stateLayout.addWidget(self.stateBar)

        return state

    def initButtons(self):
        okButton = QPushButton("Ok")
        okButton.clicked.connect(self.onOkClicked)
        cancelButton = QPushButton("Cancel")
        cancelButton.clicked.connect(self.reject)
        buttons = QWidget()
        buttonLayout = QHBoxLayout(buttons)
        buttonLayout.addWidget(okButton)
        buttonLayout.addWidget(cancelButton)

        return buttons

    def _open_pins_dialog(self):
        if not self.topology:
            return
        slave_cols = self._slave_grid_columns
        if slave_cols < 1:
            slave_cols = max(1, int(self.columns or 1))
        led_cells = None
        if self._preview_slave is not None:
            led_cells = frozenset(getattr(self._preview_slave, "led_cells", []) or [])
        dialog = TagPinsDialog(
            topology=self.topology,
            slave_grid_columns=slave_cols,
            current_colors=self.colors,
            led_cells=led_cells,
            settings=self._settings,
            on_presets_changed=self._on_presets_changed,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.colors = [list(c) for c in dialog.colors]
            self._refresh_preview()

    def changeParams(self, state):
        if state == "On":
            self._edit_colors_btn.setEnabled(True)
        else:
            self._edit_colors_btn.setEnabled(False)
        self._refresh_preview()

    def onOkClicked(self):
        action = self.stateBar.currentText()
        data = {}
        if action == "On":
            data["action"] = True
            data["colors"] = [list(c) for c in self.colors]
        else:
            data["action"] = False
            data["colors"] = _pattern_service.solid_fill(
                len(self.topology),
                [0, 0, 0],
            )
        self.tagCreated.emit(data)
        self.accept()

    def _refresh_preview(self):
        if getattr(self, "ledPreview", None) is None:
            return
        from lightconductor.application.led_preview import (
            render_canvas_with_overlay,
        )

        action_on = self.stateBar.currentText() == "On"
        if action_on:
            colors = [list(c) for c in self.colors]
        else:
            colors = [[0, 0, 0] for _ in self.topology]
        buffer = render_canvas_with_overlay(
            slave=self._preview_slave,
            time_seconds=self._preview_time,
            overlay_type_name=self._preview_type_name,
            overlay_colors=colors,
            overlay_action=action_on,
        )
        self.ledPreview.set_buffer(buffer)
