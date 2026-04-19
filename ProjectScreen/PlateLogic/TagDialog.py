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
    def __init__(self, rows, columns, topology, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
        self.topology = topology
        self.colors = []
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

        self.setLayout(self.mainLayout)
        self.changeParams("On")

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

        return colorPickerWidget

    def setColor(self):
        button = self.buttonGroup.checkedButton()
        if button:
            rgb = [self.colorPicker.rgb[0], self.colorPicker.rgb[1], self.colorPicker.rgb[2]]
            button.setColor(rgb)

    def dropColor(self):
        button = self.buttonGroup.checkedButton()
        if button:
            rgb = [0, 0, 0]
            button.setColor(rgb)

    def fillAllActiveColors(self):
        if not hasattr(self, "buttonGroup"):
            return
        rgb = [self.colorPicker.rgb[0], self.colorPicker.rgb[1], self.colorPicker.rgb[2]]
        for button in self.buttonGroup.buttons():
            if button.isEnabled():
                button.setColor(rgb)

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
