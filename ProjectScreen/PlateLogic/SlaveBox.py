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

class SlaveBox(DropBox):
    def __init__(self, title="", parent=None, boxID='', wave=None, slavePin = ''):
        super().__init__(parent)

        self.slavePin = slavePin

        self.title = title
        self.boxID = boxID

        self.wave = wave
        self.wave.manager.box = self

        self.toggleButton.setText(f"▼ {title} (pin: {slavePin})")

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
        tagWaveButtons = QWidget()
        tagWaveButtons.layout = QVBoxLayout(tagWaveButtons)
        tagWaveButtons.layout.addWidget(self.wave.chooseBox)
        tagWaveButtons.layout.addWidget(addButton)

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
        dialog = TagDialog(curType.row, curType.table, self)
        dialog.tagCreated.connect(self.wave.addTag)
        dialog.exec()

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
    def __init__(self, rows, columns, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
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
        dropButton = QPushButton("Drop color")
        dropButton.clicked.connect(self.dropColor)

        colorButtons = QWidget()
        colorButtonsLayout = QHBoxLayout(colorButtons)
        colorButtonsLayout.addWidget(setButton)
        colorButtonsLayout.addWidget(dropButton)

        colorPickerLayout.addWidget(self.colorPicker)
        colorPickerLayout.addWidget(colorButtons)

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
            self.paramsLayer.addWidget(buttons)

        elif state == "Off":
            self.deleteAllWidgets(self.paramsLayer)

    def onOkClicked(self):
        action = self.stateBar.currentText()
        data = {}
        if action=='On':
            data["action"] = "On"
            colors = []
            for layout in self.rowsLayouts:
                for i in range(layout.count()):
                    button = layout.itemAt(i).widget()
                    colors.append(button.rgb)
            data["colors"] = colors
            self.tagCreated.emit(data)
        elif action == "Off":
            data["action"] = "Off"
            colors = [[0, 0, 0] for i in range(self.columns * self.rows)]
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