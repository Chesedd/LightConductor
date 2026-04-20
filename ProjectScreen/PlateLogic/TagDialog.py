from PyQt6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QHBoxLayout, QVBoxLayout, QPushButton,
    QWidget, QComboBox, QButtonGroup)
from PyQt6.QtCore import pyqtSignal

from ProjectScreen.TagLogic.TagScreen import ColorButton
from AssistanceTools.ColorPicker import ColorPicker
from lightconductor.application.pattern_service import PatternService

_pattern_service = PatternService()


class TagDialog(QDialog):
    tagCreated = pyqtSignal(dict)
    def __init__(
        self,
        rows, columns, topology,
        parent=None,
        *,
        slave=None,
        type_name=None,
        current_time=0.0,
        led_count=0,
        settings=None,
        on_presets_changed=None,
    ):
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
        self.topology = topology
        self.colors = []
        self._preview_slave = slave
        self._preview_type_name = type_name
        self._preview_time = float(current_time or 0.0)
        self._preview_led_count = int(led_count or 0)
        self._settings = settings
        self._on_presets_changed = on_presets_changed
        self.uiCreate()

    def uiCreate(self):
        self.params = QWidget()
        self.paramsLayer = QVBoxLayout(self.params)

        self.mainScreen = QWidget()
        self.mainLayout = QHBoxLayout(self.mainScreen)
        stateWidget = QWidget()
        stateLayout = QVBoxLayout(stateWidget)
        stateLayout.addWidget(self.initStateDropBox())
        stateLayout.addWidget(self.params)
        stateLayout.addWidget(self.initButtons())

        self.mainLayout.addWidget(stateWidget)
        self.mainLayout.addWidget(self.initColorPickerWidget())

        self.ledPreview = None
        if (
            self._preview_slave is not None
            and self._preview_type_name is not None
            and self._preview_led_count > 0
        ):
            from ProjectScreen.TagLogic.LedStripView import LedStripView
            self.ledPreview = LedStripView(
                state=None, master_id=None, slave_id=None,
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

    def initColorPickerWidget(self):
        colorPickerWidget = QWidget()
        colorPickerLayout = QVBoxLayout(colorPickerWidget)

        self.colorPicker = ColorPicker()
        setButton = QPushButton("Set color")
        setButton.clicked.connect(self.setColor)
        fillButton = QPushButton("Fill active LEDs")
        fillButton.clicked.connect(self.fillAllActiveColors)
        dropButton = QPushButton("Drop color")
        dropButton.clicked.connect(self.dropColor)

        colorButtons = QWidget()
        colorButtonsLayout = QHBoxLayout(colorButtons)
        colorButtonsLayout.addWidget(setButton)
        colorButtonsLayout.addWidget(fillButton)
        colorButtonsLayout.addWidget(dropButton)

        rangeFillWidget = QWidget()
        rangeFillLayout = QHBoxLayout(rangeFillWidget)
        rangeFillLayout.addWidget(QLabel("Range from"))
        self.rangeFromBar = QLineEdit("0")
        self.rangeFromBar.setFixedWidth(50)
        rangeFillLayout.addWidget(self.rangeFromBar)
        rangeFillLayout.addWidget(QLabel("to"))
        self.rangeToBar = QLineEdit("0")
        self.rangeToBar.setFixedWidth(50)
        rangeFillLayout.addWidget(self.rangeToBar)
        fillRangeButton = QPushButton("Fill range")
        fillRangeButton.clicked.connect(self.fillRangeColors)
        rangeFillLayout.addWidget(fillRangeButton)

        colorPickerLayout.addWidget(self.colorPicker)
        colorPickerLayout.addWidget(colorButtons)
        colorPickerLayout.addWidget(rangeFillWidget)

        self.presetsBar = None
        if self._settings is not None:
            from AssistanceTools.ColorPresetsBar import ColorPresetsBar
            presets = [
                list(p) for p in (self._settings.color_presets or [])
            ]
            self.presetsBar = ColorPresetsBar(presets=presets)
            self.presetsBar.presetChosen.connect(
                self._on_preset_chosen,
            )
            self.presetsBar.addCurrentRequested.connect(
                self._on_add_current_preset,
            )
            self.presetsBar.presetsChanged.connect(
                self._on_presets_changed_internal,
            )
            colorPickerLayout.addWidget(self.presetsBar)

        self.colorPicker.colorChanged.connect(
            lambda _rgb: self._refresh_preview(),
        )

        return colorPickerWidget

    def setColor(self):
        button = self.buttonGroup.checkedButton()
        if button:
            rgb = [self.colorPicker.rgb[0], self.colorPicker.rgb[1], self.colorPicker.rgb[2]]
            button.setColor(rgb)
        self._refresh_preview()

    def dropColor(self):
        button = self.buttonGroup.checkedButton()
        if button:
            rgb = [0, 0, 0]
            button.setColor(rgb)
        self._refresh_preview()

    def fillAllActiveColors(self):
        if not hasattr(self, "buttonGroup"):
            return
        rgb = [self.colorPicker.rgb[0], self.colorPicker.rgb[1], self.colorPicker.rgb[2]]
        for button in self.buttonGroup.buttons():
            if button.isEnabled():
                button.setColor(rgb)
        self._refresh_preview()

    def fillRangeColors(self):
        if not hasattr(self, "rowsLayouts"):
            return
        try:
            start = int(self.rangeFromBar.text())
        except ValueError:
            start = 0
        try:
            end = int(self.rangeToBar.text())
        except ValueError:
            end = start
        rgb = [self.colorPicker.rgb[0], self.colorPicker.rgb[1], self.colorPicker.rgb[2]]

        ordered_buttons = []
        for cell_index in self.topology:
            row = cell_index // self.columns
            col = cell_index % self.columns
            ordered_buttons.append(self.rowsLayouts[row].itemAt(col).widget())

        current_colors = [button.rgb for button in ordered_buttons]
        updated_colors = _pattern_service.apply_fill_range(
            current_colors, start, end, rgb,
        )
        for button, color in zip(ordered_buttons, updated_colors):
            button.setColor(color)
        self._refresh_preview()

    def changeParams(self, state):
        if state == "On":
            self.deleteAllWidgets(self.paramsLayer)

            self.buttonGroup = QButtonGroup()
            self.buttonGroup.setExclusive(True)

            buttons = QWidget()
            buttonsLayout = QVBoxLayout(buttons)
            self.rowsLayouts = []
            for i in range(self.rows):
                row = QWidget()
                rowLayout = QHBoxLayout(row)
                buttonsLayout.addWidget(row)
                self.rowsLayouts.append(rowLayout)
                for j in range(self.columns):
                    button = ColorButton()
                    button.setFixedSize(20, 20)
                    button.setCheckable(True)
                    self.buttonGroup.addButton(button)
                    rowLayout.addWidget(button)
                    if (i * self.columns + j) not in self.topology:
                        button.setEnabled(False)
                        button.setText("·")
            self.paramsLayer.addWidget(buttons)
            max_index = max(0, len(self.topology) - 1)
            self.rangeFromBar.setText("0")
            self.rangeToBar.setText(str(max_index))

        elif state == "Off":
            self.deleteAllWidgets(self.paramsLayer)

        self._refresh_preview()

    def onOkClicked(self):
        action = self.stateBar.currentText()
        data = {}
        if action=='On':
            data["action"] = True
            colors = []
            for cell_index in self.topology:
                row = cell_index // self.columns
                col = cell_index % self.columns
                button = self.rowsLayouts[row].itemAt(col).widget()
                colors.append(button.rgb)
            data["colors"] = colors
            self.tagCreated.emit(data)
        elif action == "Off":
            data["action"] = False
            colors = _pattern_service.solid_fill(len(self.topology), [0, 0, 0])
            data["colors"] = colors
            self.tagCreated.emit(data)
        self.accept()

    def _refresh_preview(self):
        if getattr(self, "ledPreview", None) is None:
            return
        from lightconductor.application.led_preview import (
            render_led_strip_with_overlay,
        )
        action_on = self.stateBar.currentText() == "On"
        if action_on and hasattr(self, "rowsLayouts"):
            colors = []
            for cell_index in self.topology:
                row = cell_index // self.columns
                col = cell_index % self.columns
                btn = self.rowsLayouts[row].itemAt(col).widget()
                colors.append(list(btn.rgb))
        else:
            colors = [[0, 0, 0] for _ in self.topology]
        buffer = render_led_strip_with_overlay(
            slave=self._preview_slave,
            time_seconds=self._preview_time,
            overlay_type_name=self._preview_type_name,
            overlay_colors=colors,
            overlay_action=action_on,
        )
        self.ledPreview.set_buffer(buffer)

    def _on_preset_chosen(self, rgb):
        self.colorPicker.setColor(list(rgb))

    def _on_add_current_preset(self):
        if self.presetsBar is None:
            return
        rgb = list(self.colorPicker.rgb)
        self.presetsBar.add_preset(rgb)

    def _on_presets_changed_internal(self, presets):
        if self._on_presets_changed is None:
            return
        self._on_presets_changed(
            [list(p) for p in presets],
        )

    def deleteAllWidgets(self, layout):
        if layout is None:
            return

        while layout.count():
            item = layout.takeAt(0)

            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

            elif item.layout() is not None:
                self.deleteAllWidgets(item.layout())
