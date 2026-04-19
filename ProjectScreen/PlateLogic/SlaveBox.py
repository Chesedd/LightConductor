from PyQt6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QHBoxLayout, QVBoxLayout, QPushButton,
    QWidget, QMenu, QComboBox, QButtonGroup)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction

from AssistanceTools.SimpleDialog import SimpleDialog
from AssistanceTools.TagState import TagState
from ProjectScreen.TagLogic.TagScreen import TagInfoScreen, ColorButton
from AssistanceTools.FlowLayout import FlowLayout
from AssistanceTools.ColorPicker import ColorPicker
from AssistanceTools.DropBox import DropBox
import bisect
from lightconductor.application.pattern_service import PatternService

_pattern_service = PatternService()

class SlaveBox(DropBox):
    def __init__(self, title="", parent=None, boxID='', wave=None, slavePin = '', ledCount=0):
        super().__init__(parent)

        self.slavePin = slavePin
        self.ledCount = ledCount

        self.title = title
        self.boxID = boxID

        self.wave = wave
        self.wave.manager.box = self

        self.toggleButton.setText(f"▼ {title} (pin: {slavePin}, leds: {ledCount})")

        self.initUI()

    def initUI(self):
        self.wave.positionUpdate.connect(self.onPositionUpdate)
        self.wave.manager.newTypeCreate.connect(self.addTagState)

        waveWidget = QWidget()
        waveWidget.layout = QVBoxLayout(waveWidget)
        waveWidget.layout.addWidget(self.initWaveButtons())
        waveWidget.layout.addWidget(self.wave)

        waveSpace = QWidget()
        waveSpace.layout = QHBoxLayout(waveSpace)
        waveSpace.layout.addWidget(self.initTagWaveButtons())
        waveSpace.layout.addWidget(waveWidget)

        tagsWidget = QWidget()
        self.tagsLayout = FlowLayout()
        tagsWidget.setLayout(self.tagsLayout)

        centralWidget = QWidget()
        centralWidget.layout = QVBoxLayout(centralWidget)
        centralWidget.layout.addWidget(waveSpace)
        centralWidget.layout.addWidget(tagsWidget)

        self.tagInfo = TagInfoScreen(tagTypes=self.wave.manager.types)
        self.wave.manager.tagScreen = self.tagInfo

        self.mainWidget = QWidget()
        self.mainLayout = QHBoxLayout(self.mainWidget)
        self.mainLayout.addWidget(centralWidget, 3)
        self.mainLayout.addWidget(self.wave.manager, 2)
        self.mainLayout.addWidget(self.tagInfo, 1)

        self.addWidget(self.mainWidget)

    def initTagWaveButtons(self):
        addButton = QPushButton("Add tag")
        addButton.clicked.connect(self.createTag)
        addGroupButton = QPushButton("Add tag group")
        addGroupButton.clicked.connect(self.createTagGroup)
        tagWaveButtons = QWidget()
        tagWaveButtons.layout = QVBoxLayout(tagWaveButtons)
        tagWaveButtons.layout.addWidget(self.wave.chooseBox)
        tagWaveButtons.layout.addWidget(addButton)
        tagWaveButtons.layout.addWidget(addGroupButton)

        return tagWaveButtons

    def initWaveButtons(self):
        waveButtons = QWidget()
        waveButtons.layout = QHBoxLayout(waveButtons)
        self.playButton = QPushButton("Play")
        self.playButton.clicked.connect(self.playOrPause)
        self.playAndPauseButton = QPushButton("Play+Pause")
        self.playAndPauseButton.clicked.connect(self.wave.playAndPause)
        self.timeLabel = QLabel("time")
        waveButtons.layout.addWidget(self.playButton)
        waveButtons.layout.addWidget(self.playAndPauseButton)
        waveButtons.layout.addWidget(self.timeLabel)

        return waveButtons

    def playOrPause(self):
        state = self.playButton.text()
        if state == "Play":
            self.playButton.setText("Pause")
        else:
            self.playButton.setText("Play")
        self.wave.playOrPause(state)

    def addTagState(self, tagType):
        state = TagState(tagType)
        self.tagsLayout.addWidget(state)

    def createTag(self):
        curType = self.wave.manager.curType
        if curType is None:
            return
        dialog = TagDialog(curType.row, curType.table, curType.topology, self)
        dialog.tagCreated.connect(self.wave.addTag)
        dialog.exec()

    def createTagGroup(self):
        curType = self.wave.manager.curType
        if curType is None:
            return
        led_count = len(curType.topology)
        dialog = TagGroupPatternDialog(led_count=led_count, parent=self)
        if dialog.exec():
            for tag_data in dialog.buildTags():
                self.wave.addTagAtTime(
                    {
                        "action": tag_data["action"],
                        "colors": tag_data["colors"],
                    },
                    tag_data["time"],
                )

    def onPositionUpdate(self, time, timeStr):
        for i in range(self.tagsLayout.count()):
            widget = self.tagsLayout.itemAt(i).widget()
            tags = widget.tagType.tags
            times = [tag.time for tag in tags]
            pos = bisect.bisect_right(times, time) - 1
            if pos >= 0:
                tag = tags[pos]
                widget.changeState(tag.action)
            else:
                widget.changeState(False)
        self.timeLabel.setText(timeStr)

    def contextMenuEvent(self, a0):
        menu = QMenu(self)

        renameAction = QAction("Rename", self)
        renameAction.triggered.connect(self.showRenameDialog)
        menu.addAction(renameAction)

        deleteAction = QAction("Delete", self)
        deleteAction.triggered.connect(self.showDeleteDialog)
        menu.addAction(deleteAction)

        menu.exec(a0.globalPos())

    def addWidget(self, widget):
        self.contentLayout.addWidget(widget)

    def removeWidget(self, widget):
        self.contentLayout.removeWidget(widget)
        widget.setParent(None)

    def clear(self):
        while self.contentLayout.count():
            child = self.contentLayout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def showRenameDialog(self):
        dialog = RenameDialog(self)
        dialog.boxRenamed.connect(self.renameBox)
        dialog.exec()

    def renameBox(self, newTitle):
        self.toggleButton.setText("▼ " + newTitle)

    def showDeleteDialog(self):
        dialog = DeleteDialog(self)
        dialog.boxDelete.connect(self.deleteBox)
        dialog.exec()

    def deleteBox(self):
        self.boxDeleted.emit(self.boxID)
        self.deleteLater()


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
            data["action"] = "On"
            colors = []
            for cell_index in self.topology:
                row = cell_index // self.columns
                col = cell_index % self.columns
                button = self.rowsLayouts[row].itemAt(col).widget()
                colors.append(button.rgb)
            data["colors"] = colors
            self.tagCreated.emit(data)
        elif action == "Off":
            data["action"] = "Off"
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


class TagGroupPatternDialog(QDialog):
    def __init__(self, led_count, parent=None):
        super().__init__(parent)
        self.led_count = led_count
        self.setWindowTitle("Tag group patterns")
        self.mainLayout = QVBoxLayout(self)
        self.initUI()

    def initUI(self):
        patternRow = QWidget()
        patternLayout = QHBoxLayout(patternRow)
        patternLayout.addWidget(QLabel("Pattern"))
        self.patternBar = QComboBox()
        self.patternBar.addItems([
            "Sequential fill",
            "Floating gradient",
            "Moving window",
        ])
        self.patternBar.currentTextChanged.connect(self.onPatternChanged)
        patternLayout.addWidget(self.patternBar)
        self.mainLayout.addWidget(patternRow)

        timingRow = QWidget()
        timingLayout = QHBoxLayout(timingRow)
        timingLayout.addWidget(QLabel("Start"))
        self.startTimeBar = QLineEdit("0.0")
        self.startTimeBar.setFixedWidth(60)
        timingLayout.addWidget(self.startTimeBar)
        timingLayout.addWidget(QLabel("End"))
        self.endTimeBar = QLineEdit("5.0")
        self.endTimeBar.setFixedWidth(60)
        timingLayout.addWidget(self.endTimeBar)
        timingLayout.addWidget(QLabel("Step"))
        self.stepBar = QLineEdit("0.2")
        self.stepBar.setFixedWidth(60)
        timingLayout.addWidget(self.stepBar)
        self.mainLayout.addWidget(timingRow)

        extraRow = QWidget()
        extraLayout = QHBoxLayout(extraRow)
        extraLayout.addWidget(QLabel("Window LEDs"))
        self.windowSizeBar = QLineEdit("3")
        self.windowSizeBar.setFixedWidth(60)
        extraLayout.addWidget(self.windowSizeBar)
        extraLayout.addWidget(QLabel("Gradient width"))
        self.gradientWidthBar = QLineEdit("4")
        self.gradientWidthBar.setFixedWidth(60)
        extraLayout.addWidget(self.gradientWidthBar)
        self.mainLayout.addWidget(extraRow)

        self.colorPicker = ColorPicker()
        self.mainLayout.addWidget(self.colorPicker)

        buttons = QWidget()
        buttonsLayout = QHBoxLayout(buttons)
        okButton = QPushButton("Create")
        okButton.clicked.connect(self.accept)
        cancelButton = QPushButton("Cancel")
        cancelButton.clicked.connect(self.reject)
        buttonsLayout.addWidget(okButton)
        buttonsLayout.addWidget(cancelButton)
        self.mainLayout.addWidget(buttons)
        self.onPatternChanged(self.patternBar.currentText())

    def onPatternChanged(self, pattern_name):
        self.windowSizeBar.setEnabled(pattern_name == "Moving window")
        self.gradientWidthBar.setEnabled(pattern_name == "Floating gradient")

    def _parse_float(self, line_edit, default):
        try:
            return float(line_edit.text())
        except ValueError:
            return default

    def _parse_int(self, line_edit, default):
        try:
            return int(line_edit.text())
        except ValueError:
            return default

    def buildTags(self):
        rgb = [self.colorPicker.rgb[0], self.colorPicker.rgb[1], self.colorPicker.rgb[2]]
        start_time = self._parse_float(self.startTimeBar, 0.0)
        end_time = self._parse_float(self.endTimeBar, start_time)
        step = self._parse_float(self.stepBar, 0.2)
        pattern_name = self.patternBar.currentText()

        if pattern_name == "Sequential fill":
            frames = _pattern_service.sequential_fill(self.led_count, rgb)
        elif pattern_name == "Floating gradient":
            width = self._parse_int(self.gradientWidthBar, 4)
            frames = _pattern_service.floating_gradient(
                self.led_count, rgb, width,
            )
        else:
            window = self._parse_int(self.windowSizeBar, 3)
            frames = _pattern_service.moving_window(
                self.led_count, window, rgb,
            )

        return _pattern_service.build_tags(
            frames=frames,
            start_time=start_time,
            end_time=end_time,
            step=step,
        )

class RenameDialog(SimpleDialog):
    boxRenamed = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        self.mainLayout = QVBoxLayout(self)

        self.setWindowTitle("Rename box")
        newNameText = QLabel("Insert new title")
        self.newNameBar = QLineEdit()
        self.newNameParams = QWidget()
        newNameLayout = QHBoxLayout(self.newNameParams)
        newNameLayout.addWidget(newNameText)
        newNameLayout.addWidget(self.newNameBar)
        self.mainLayout.addWidget(self.newNameParams)

        okBtn = self.OkAndCancel()
        okBtn.clicked.connect(self.onOkClicked)


    def onOkClicked(self):
        self.boxRenamed.emit(self.newNameBar.text())
        self.accept()

class DeleteDialog(QDialog):
    boxDelete = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Delete box")
        newNameText = QLabel("Are you sure?")

        self.buttons = QWidget()
        buttonsLayout = QHBoxLayout(self.buttons)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.onOkClicked)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttonsLayout.addWidget(ok_btn)
        buttonsLayout.addWidget(cancel_btn)

        self.mainLayout = QVBoxLayout()
        self.mainLayout.addWidget(newNameText)
        self.mainLayout.addWidget(self.buttons)
        self.setLayout(self.mainLayout)

    def onOkClicked(self):
        self.boxDelete.emit()
        self.accept()
