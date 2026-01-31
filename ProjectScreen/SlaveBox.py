from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import QAction
from AssistanceTools.TagState import TagState
from ProjectScreen.TagScreen import TagInfoScreen
from AssistanceTools.FlowLayout import FlowLayout
from AssistanceTools.ColorPicker import ColorPicker
import bisect

class SlaveBox(QWidget):
    boxDeleted = pyqtSignal(str)
    def __init__(self, title="", parent=None, boxID='', wave=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mainLayout.setSpacing(0)

        self.title = title
        self.boxID = boxID

        self.wave = wave
        self.wave.manager.box = self

        self.createTitleButton()
        self.createContentArea()

        self.mainLayout.addWidget(self.toggleButton)
        self.mainLayout.addWidget(self.contentArea)

        self.toggleButton.setText("▼ "+title)

        self.initUI()

    def initUI(self):
        self.wave.positionUpdate.connect(self.onPositionUpdate)
        self.wave.manager.newTypeCreate.connect(self.addTagState)

        addButton = QPushButton("Add tag")
        addButton.clicked.connect(self.createTag)
        tagWaveButtons = QWidget()
        tagWaveButtons.layout = QVBoxLayout(tagWaveButtons)
        tagWaveButtons.layout.addWidget(self.wave.chooseBox)
        tagWaveButtons.layout.addWidget(addButton)

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

        waveWidget = QWidget()
        waveWidget.layout = QVBoxLayout(waveWidget)
        waveWidget.layout.addWidget(waveButtons)
        waveWidget.layout.addWidget(self.wave)

        waveSpace = QWidget()
        waveSpace.layout = QHBoxLayout(waveSpace)
        waveSpace.layout.addWidget(tagWaveButtons)
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

        mainWidget = QWidget()
        mainWidget.layout = QHBoxLayout(mainWidget)
        mainWidget.layout.addWidget(centralWidget, 3)
        mainWidget.layout.addWidget(self.wave.manager, 2)
        mainWidget.layout.addWidget(self.tagInfo, 1)

        self.addWidget(mainWidget)

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
                widget.changeState(tag.state)
            else:
                widget.changeState(False)
        self.timeLabel.setText(timeStr)

    def createTitleButton(self):
        self.toggleButton = QPushButton()
        self.toggleButton.setCheckable(True)
        self.toggleButton.setChecked(False)
        self.toggleButton.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 8px;
                border: 1px solid #ccc;
                background-color: #f0f0f0;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:checked {
                background-color: #d0d0d0;
                border-bottom: none;
            }
        """)
        self.toggleButton.toggled.connect(self.onToggled)

    def createContentArea(self):
        self.contentArea = QScrollArea()
        self.contentArea.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.contentArea.setMaximumHeight(0)
        self.contentArea.setMinimumHeight(0)
        self.contentArea.setFrameShape(QFrame.Shape.NoFrame)
        self.contentArea.setWidgetResizable(True)

        self.contentWidget = QWidget()
        self.contentLayout = QVBoxLayout(self.contentWidget)
        self.contentLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.contentLayout.setSpacing(5)
        self.contentLayout.setContentsMargins(10, 10, 10, 10)
        self.contentArea.setWidget(self.contentWidget)


    def contextMenuEvent(self, a0):
        menu = QMenu(self)

        renameAction = QAction("Rename", self)
        renameAction.triggered.connect(self.showRenameDialog)
        menu.addAction(renameAction)

        deleteAction = QAction("Delete", self)
        deleteAction.triggered.connect(self.showDeleteDialog)
        menu.addAction(deleteAction)

        menu.exec(a0.globalPos())

    def onToggled(self, checked):
        if checked:
            self.toggleButton.setText("► " + self.toggleButton.text()[2:])
            self.contentArea.setMaximumHeight(16777215)
            self.contentArea.setMinimumHeight(200)
        else:
            self.toggleButton.setText("▼ " + self.toggleButton.text()[2:])
            self.contentArea.setMaximumHeight(0)
            self.contentArea.setMinimumHeight(0)

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


class ColorButton(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.rgb = [0, 0, 0]
        self.setStyleSheet("""
                                QPushButton {
                                    background-color: black;
                                }
                                QPushButton:checked {
                                    border: 2px solid #ff9900; 
                                    padding: 11px;
                                }
                            """)


    def setColor(self, rgb):
        self.rgb = rgb
        self.setStyleSheet("""
                                QPushButton {
                                """
                                    f"background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]});"
                                """
                                }
                                QPushButton:checked {
                                    border: 2px solid #ff9900; 
                                    padding: 11px;
                                }
                            """)



class TagDialog(QDialog):
    tagCreated = pyqtSignal(dict)
    def __init__(self, rows, columns, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
        self.colors = []
        self.uiCreate()

    def uiCreate(self):
        print(self.rows)
        stateText = QLabel("Состояние")
        self.stateBar = QComboBox()
        self.stateBar.addItems(["On", "Off"])
        self.stateBar.currentTextChanged.connect(self.changeParams)
        state = QWidget()
        stateLayout = QHBoxLayout(state)
        stateLayout.addWidget(stateText)
        stateLayout.addWidget(self.stateBar)

        self.params = QWidget()
        self.paramsLayer = QVBoxLayout(self.params)

        okButton = QPushButton("Ok")
        okButton.clicked.connect(self.onOkClicked)
        cancelButton = QPushButton("Cancel")
        cancelButton.clicked.connect(self.reject)
        buttons = QWidget()
        buttonLayout = QHBoxLayout(buttons)
        buttonLayout.addWidget(okButton)
        buttonLayout.addWidget(cancelButton)

        self.mainScreen = QWidget()
        self.mainLayout = QHBoxLayout(self.mainScreen)
        stateWidget = QWidget()
        stateLayout = QVBoxLayout(stateWidget)
        stateLayout.addWidget(state)
        stateLayout.addWidget(self.params)
        stateLayout.addWidget(buttons)

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

        self.mainLayout.addWidget(stateWidget)
        self.mainLayout.addWidget(colorPickerWidget)

        self.setLayout(self.mainLayout)

    def setColor(self):
        button = self.buttonGroup.checkedButton()
        if button:
            rgb = [self.colorPicker.r, self.colorPicker.g, self.colorPicker.b]
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
                self.deleteAllWidgets(item.layout())  #

class RenameDialog(QDialog):
    boxRenamed = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Rename box")
        newNameText = QLabel("Insert new title")
        self.newNameBar = QLineEdit()
        self.newNameParams = QWidget()
        newNameLayout = QHBoxLayout(self.newNameParams)
        newNameLayout.addWidget(newNameText)
        newNameLayout.addWidget(self.newNameBar)

        self.buttons = QWidget()
        buttonsLayout = QHBoxLayout(self.buttons)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.on_ok_clicked)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttonsLayout.addWidget(ok_btn)
        buttonsLayout.addWidget(cancel_btn)

        self.mainLayout = QVBoxLayout()
        self.mainLayout.addWidget(self.newNameParams)
        self.mainLayout.addWidget(self.buttons)
        self.setLayout(self.mainLayout)

    def on_ok_clicked(self):
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
        ok_btn.clicked.connect(self.on_ok_clicked)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttonsLayout.addWidget(ok_btn)
        buttonsLayout.addWidget(cancel_btn)

        self.mainLayout = QVBoxLayout()
        self.mainLayout.addWidget(newNameText)
        self.mainLayout.addWidget(self.buttons)
        self.setLayout(self.mainLayout)

    def on_ok_clicked(self):
        self.boxDelete.emit()
        self.accept()