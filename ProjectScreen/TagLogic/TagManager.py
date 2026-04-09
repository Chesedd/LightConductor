from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QDialog,
                             QLabel, QLineEdit, QToolButton, QButtonGroup, QMenu, QScrollArea, QComboBox)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from ProjectScreen.TagLogic.TagType import TagType
from AssistanceTools.ColorPicker import ColorPicker
import pyqtgraph as pg
from PyQt6.QtGui import QColor
from ProjectScreen.PlateLogic.SlaveBox import DeleteDialog
from AssistanceTools.FlowLayout import FlowLayout
from AssistanceTools.SimpleDialog import SimpleDialog
from lightconductor.application.range_allocator import available_starts

class TagManager(QWidget):
    newTypeCreate = pyqtSignal(TagType)
    def __init__(self, checkBox):
        super().__init__()
        self.checkBox = checkBox
        self.buttons = QButtonGroup()
        self.buttons.setExclusive(True)
        self.curType = None
        self.types = {}
        self.box = None
        self.tagScreen = None

        self.initPanel()

    def initPanel(self):
        self.mainWidget = QWidget()
        self.mainLayout = QVBoxLayout(self.mainWidget)
        self.setLayout(self.mainLayout)

        self.scrollArea = QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setMaximumHeight(200)
        self.innerWidget = QWidget()
        self.innerArea = FlowLayout()
        self.innerWidget.setLayout(self.innerArea)
        self.scrollArea.setWidget(self.innerWidget)

        addButton = QPushButton("+ Add range")
        addButton.clicked.connect(self.showNewTypeDialog)
        self.innerArea.addWidget(addButton)
        self.mainLayout.addWidget(self.scrollArea)

    def showNewTypeDialog(self):
        led_count = self.box.ledCount if self.box else 0
        dialog = newTypeDialog(self, led_count=led_count, occupied_ranges=self.getOccupiedRanges())
        dialog.newType.connect(self.addType)
        dialog.exec()

    def getOccupiedRanges(self):
        ranges = []
        for tag_type in self.types.values():
            try:
                start = int(tag_type.pin)
            except ValueError:
                start = 0
            size = int(tag_type.row) * int(tag_type.table)
            ranges.append((start, size))
        return ranges

    def addType(self, params):
        newType = TagType(params["color"], params["name"], params["pin"], params["row"], params["table"])
        self.types[params["name"]] = newType
        button = TagButton(newType, manager=self)
        button.setCheckable(True)
        button.clicked.connect(self.setNewType)
        self.buttons.addButton(button)
        self.innerArea.insertWidget(0, button)

        self.checkBox.addType(params["name"])
        self.newTypeCreate.emit(newType)
        return newType

    def setNewType(self):
        self.curType = self.buttons.checkedButton().tagType

class editDialog(SimpleDialog):
    editType = pyqtSignal(dict)

    def __init__(self, parent=None, tagType = None):
        super().__init__(parent=parent)
        self.type = tagType
        self.setWindowTitle(self.type.name)
        self.mainLayout = QVBoxLayout(self)
        self.initParams()

    def initParams(self):
        self.newNameBar = self.LabelAndLine("Name")

        self.colorPicker = ColorPicker()
        color = self.type.color
        rgb = list(map(int, color.split(',')))
        for i in range(3):
            self.colorPicker.slidersLabels[i][0].setValue(rgb[i])
        self.layout().addWidget(self.colorPicker)

        self.newPinBar = self.LabelAndLine("Segment start")

        okBtn = self.OkAndCancel()
        okBtn.clicked.connect(self.onOkClicked)

    def onOkClicked(self):
        params = {
            "name": self.newNameBar.text(),
            "color": f"{self.colorPicker.rgb[0]}, {self.colorPicker.rgb[1]}, {self.colorPicker.rgb[2]}",
            "pin": self.newPinBar.text()
        }
        self.editType.emit(params)
        self.accept()

class newTypeDialog(SimpleDialog):
    newType = pyqtSignal(dict)
    def __init__(self, parent=None, led_count=0, occupied_ranges=None):
        super().__init__(parent=parent)
        self.setWindowTitle("New range")
        self.led_count = led_count
        self.occupied_ranges = occupied_ranges or []
        self.mainLayout = QVBoxLayout(self)
        self.initParams()

    def initParams(self):
        self.newNameBar = self.LabelAndLine("Name")

        self.colorPicker = ColorPicker()
        self.layout().addWidget(self.colorPicker)

        self.rangeLengthBar = self.LabelAndLine("Range length")
        self.rangeLengthBar.setText("1")

        self.rangeStartLabel = QLabel("Range start")
        self.rangeStartCombo = QComboBox()
        rangeStartWidget = QWidget()
        rangeStartLayout = QHBoxLayout(rangeStartWidget)
        rangeStartLayout.addWidget(self.rangeStartLabel)
        rangeStartLayout.addWidget(self.rangeStartCombo)
        self.layout().addWidget(rangeStartWidget)

        self.rangeLengthBar.textChanged.connect(self.refreshStartChoices)
        self.refreshStartChoices()

        okBtn = self.OkAndCancel()
        okBtn.clicked.connect(self.onOkClicked)

    def refreshStartChoices(self):
        try:
            length = int(self.rangeLengthBar.text())
        except ValueError:
            length = 1
        starts = available_starts(self.led_count, self.occupied_ranges, length)
        if not starts and self.led_count == 0:
            starts = [0]
        self.rangeStartCombo.clear()
        self.rangeStartCombo.addItems([str(start) for start in starts])

    def onOkClicked(self):
        try:
            length = int(self.rangeLengthBar.text())
        except ValueError:
            length = 1
        start = self.rangeStartCombo.currentText() or "0"
        params = {
            "name": self.newNameBar.text(),
            "color": f"{self.colorPicker.rgb[0]}, {self.colorPicker.rgb[1]}, {self.colorPicker.rgb[2]}",
            "pin": start,
            "row": 1,
            "table": length,
        }
        self.newType.emit(params)
        self.accept()

class TagButton(QToolButton):
    def __init__(self, tagType, manager=None):
        super().__init__()
        self.manager = manager
        self.tagType = tagType
        self.setFixedSize(200, 80)
        self.mainLayout = QVBoxLayout(self)

        self.initButton()


    def initButton(self):
        container = QWidget()
        containerLayout = QHBoxLayout(container)
        self.setFixedSize(100, 100)

        self.color = QLabel()
        self.color.setFixedSize(10, 10)
        self.color.setStyleSheet(
            f"background-color: rgb({self.tagType.color});"
            "border-radius: 5px;"
        )

        self.name = QLabel(self.tagType.name)
        self.pin = QLabel(f"seg:{self.tagType.pin}")

        containerLayout.addWidget(self.color)
        containerLayout.addWidget(self.name)
        containerLayout.addWidget(self.pin)

        self.mainLayout.addWidget(container)

    def contextMenuEvent(self, a0):
        menu = QMenu(self)

        renameAction = QAction("Edit", self)
        renameAction.triggered.connect(self.showEditDialog)
        menu.addAction(renameAction)

        deleteAction = QAction("Delete", self)
        deleteAction.triggered.connect(self.showDeleteDialog)
        menu.addAction(deleteAction)

        menu.exec(a0.globalPos())

    def showEditDialog(self):
        dialog = editDialog(tagType=self.tagType)
        dialog.editType.connect(self.editType)
        dialog.exec()

    def editType(self, params):
        self.tagType.name = params["name"]
        self.tagType.color = params["color"]
        self.tagType.pin = params["pin"]
        self.editButton()
        r, g, b = map(int, self.tagType.color.split(','))
        for tag in self.tagType.tags:
            tag.setPen(pg.mkPen(QColor(r, g, b), width=1))

    def editButton(self):
        self.color.setStyleSheet(
            f"background-color: rgb({self.tagType.color});"
            "border-radius: 5px;"
        )

        self.name = QLabel(self.tagType.name)
        self.pin = QLabel(f"seg:{self.tagType.pin}")


    def showDeleteDialog(self):
        dialog = DeleteDialog(self)
        dialog.boxDelete.connect(self.deleteType)
        dialog.exec()

    def deleteType(self):
        for tag in self.tagType.tags:
            tag.scene().removeItem(tag)
        del self.manager.types[self.tagType.name]
        states = self.manager.box.tagsLayout
        for i in range(states.count()):
            state = states.itemAt(i).widget()
            if state.tagType.name == self.tagType.name:
                state.deleteLater()
        self.deleteLater()
