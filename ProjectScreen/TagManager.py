from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QDialog,
                             QLabel, QLineEdit, QToolButton, QButtonGroup, QMenu, QScrollArea)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from ProjectScreen.TagType import TagType
from AssistanceTools.ColorPicker import ColorPicker
import pyqtgraph as pg
from PyQt6.QtGui import QColor
from ProjectScreen.SlaveBox import DeleteDialog

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
        self.innerArea = QVBoxLayout()
        self.innerWidget.setLayout(self.innerArea)
        self.scrollArea.setWidget(self.innerWidget)

        addButton = QPushButton("+ Add type")
        addButton.clicked.connect(self.showNewTypeDialog)
        self.innerArea.addWidget(addButton)
        self.mainLayout.addWidget(self.scrollArea)

    def showNewTypeDialog(self):
        dialog = newTypeDialog(self)
        dialog.newType.connect(self.addType)
        dialog.exec()

    def addType(self, params):
        newType = TagType(params["color"], params["name"], params["pin"])
        self.types[params["name"]] = newType
        button = TagButton(newType, manager=self)
        button.setCheckable(True)
        button.clicked.connect(self.setNewType)
        self.buttons.addButton(button)
        self.innerArea.insertWidget(0, button)
        self.checkBox.addType(params["name"])
        self.newTypeCreate.emit(newType)

    def setNewType(self):
        self.curType = self.buttons.checkedButton().tagType

class editDialog(QDialog):
    editType = pyqtSignal(dict)

    def __init__(self, parent=None, tagType = None):
        super().__init__(parent=parent)
        self.type = tagType
        self.setWindowTitle(self.type.name)
        self.mainWidget = QWidget()
        self.mainLayout = QVBoxLayout(self.mainWidget)
        self.initParams()
        self.initButtons()
        self.setLayout(self.mainLayout)

    def initParams(self):
        self.newTypeParams = QWidget()
        newTypeLayout = QVBoxLayout(self.newTypeParams)

        newName = QWidget()
        newNameText = QLabel("Name")
        self.newNameBar = QLineEdit(self.type.name)
        newNameLayout = QHBoxLayout(newName)
        newNameLayout.addWidget(newNameText)
        newNameLayout.addWidget(self.newNameBar)

        self.colorPicker = ColorPicker()
        color = self.type.color
        r, g, b = map(int, color.split(','))
        self.colorPicker.sliderR.setValue(r)
        self.colorPicker.sliderG.setValue(g)
        self.colorPicker.sliderB.setValue(b)

        newPin = QWidget()
        newPinText = QLabel("Pin")
        self.newPinBar = QLineEdit(self.type.pin)
        newPinLayout = QHBoxLayout(newPin)
        newPinLayout.addWidget(newPinText)
        newPinLayout.addWidget(self.newPinBar)

        newTypeLayout.addWidget(newName)
        newTypeLayout.addWidget(self.colorPicker)
        newTypeLayout.addWidget(newPin)

        self.mainLayout.addWidget(self.newTypeParams)

    def initButtons(self):
        self.buttons = QWidget()
        buttonsLayout = QHBoxLayout(self.buttons)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.on_ok_clicked)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttonsLayout.addWidget(ok_btn)
        buttonsLayout.addWidget(cancel_btn)

        self.mainLayout.addWidget(self.buttons)

    def on_ok_clicked(self):
        params = {
            "name": self.newNameBar.text(),
            "color": f"{self.colorPicker.r}, {self.colorPicker.g}, {self.colorPicker.b}",
            "pin": self.newPinBar.text()
        }
        self.editType.emit(params)
        self.accept()

class newTypeDialog(QDialog):
    newType = pyqtSignal(dict)
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle("New tag type")
        self.mainWidget = QWidget()
        self.mainLayout = QVBoxLayout(self.mainWidget)
        self.initParams()
        self.initButtons()
        self.setLayout(self.mainLayout)

    def initParams(self):
        self.newTypeParams = QWidget()
        newTypeLayout = QVBoxLayout(self.newTypeParams)

        newName = QWidget()
        newNameText = QLabel("Name")
        self.newNameBar = QLineEdit()
        newNameLayout = QHBoxLayout(newName)
        newNameLayout.addWidget(newNameText)
        newNameLayout.addWidget(self.newNameBar)

        self.colorPicker = ColorPicker()

        newPin = QWidget()
        newPinText = QLabel("Pin")
        self.newPinBar = QLineEdit()
        newPinLayout = QHBoxLayout(newPin)
        newPinLayout.addWidget(newPinText)
        newPinLayout.addWidget(self.newPinBar)

        newTypeLayout.addWidget(newName)
        newTypeLayout.addWidget(self.colorPicker)
        newTypeLayout.addWidget(newPin)

        self.mainLayout.addWidget(self.newTypeParams)

    def initButtons(self):
        self.buttons = QWidget()
        buttonsLayout = QHBoxLayout(self.buttons)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.on_ok_clicked)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttonsLayout.addWidget(ok_btn)
        buttonsLayout.addWidget(cancel_btn)

        self.mainLayout.addWidget(self.buttons)

    def on_ok_clicked(self):
        params = {
            "name": self.newNameBar.text(),
            "color": f"{self.colorPicker.r}, {self.colorPicker.g}, {self.colorPicker.b}",
            "pin": self.newPinBar.text()
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
        self.pin = QLabel(self.tagType.pin)

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
        self.pin = QLabel(self.tagType.pin)


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


