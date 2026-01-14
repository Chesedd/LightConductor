from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QDialog,
                             QLabel, QLineEdit, QToolButton)
from PyQt6.QtCore import pyqtSignal
from ProjectScreen.TagType import TagType
from AssistanceTools.ColorPicker import ColorPicker

class TagManager(QWidget):

    def __init__(self):
        super().__init__()
        self.initPanel()

    def initPanel(self):
        self.mainWidget = QWidget()
        self.mainLayout = QVBoxLayout(self.mainWidget)
        self.setLayout(self.mainLayout)

        addButton = QPushButton("+ Add type")
        addButton.clicked.connect(self.showNewTypeDialog)
        self.mainLayout.addWidget(addButton)

    def showNewTypeDialog(self):
        dialog = newTypeDialog(self)
        dialog.newType.connect(self.addType)
        dialog.exec()

    def addType(self, params):
        newType = TagType(params["color"], params["name"], params["pin"])
        button = TagButton(newType)
        self.mainLayout.insertWidget(0, button)

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
            "color": "base",
            "pin": self.newPinBar.text()
        }
        self.newType.emit(params)
        self.accept()

class TagButton(QToolButton):
    def __init__(self, tagType):
        super().__init__()
        self.tagType = tagType
        self.setFixedSize(200, 80)
        self.mainLayout = QVBoxLayout(self)

        self.initButton()


    def initButton(self):
        container = QWidget()
        containerLayout = QHBoxLayout(container)

        name = QLabel(self.tagType.name+" ")
        color = QLabel(self.tagType.color+" ")
        pin = QLabel(self.tagType.pin)

        containerLayout.addWidget(name)
        containerLayout.addWidget(color)
        containerLayout.addWidget(pin)

        self.mainLayout.addWidget(container)