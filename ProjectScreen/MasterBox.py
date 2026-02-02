from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import QAction
from AssistanceTools.TagState import TagState
from ProjectScreen.TagScreen import TagInfoScreen
from ProjectScreen.SlaveBox import SlaveBox
import bisect
from ProjectScreen.TagManager import TagManager
from datetime import datetime
from AssistanceTools.ChooseBox import  TagTypeChooseBox
from ProjectScreen.WaveWidget import WaveWidget


class newSlaveDialog(QDialog):
    slaveCreated = pyqtSignal(dict)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.uiCreate()

    def uiCreate(self):
        slaveNameText = QLabel("Slave's name")
        self.slaveNameBar = QLineEdit()
        slaveNameLayout = QHBoxLayout()
        slaveNameLayout.addWidget(slaveNameText)
        slaveNameLayout.addWidget(self.slaveNameBar)

        pinText = QLabel("Slave pin")
        self.pinBar = QLineEdit()
        pinLayout = QHBoxLayout()
        pinLayout.addWidget(pinText)
        pinLayout.addWidget(self.pinBar)

        okButton = QPushButton("Ok")
        okButton.clicked.connect(self.onOkClicked)
        cancelButton = QPushButton("Cancel")
        cancelButton.clicked.connect(self.reject)
        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(okButton)
        buttonLayout.addWidget(cancelButton)

        self.mainScreen = QWidget()
        self.mainLayout = QVBoxLayout(self.mainScreen)
        self.mainLayout.addLayout(slaveNameLayout)
        self.mainLayout.addLayout(pinLayout)
        self.mainLayout.addLayout(buttonLayout)

        self.setLayout(self.mainLayout)

    def onOkClicked(self):
        data = {}
        data["name"] = self.slaveNameBar.text()
        data["pin"] = self.pinBar.text()
        self.slaveCreated.emit(data)
        self.accept()

class MasterBox(QWidget):
    boxDeleted = pyqtSignal(str)
    def __init__(self, title="", parent=None, boxID='', audio=None, sr=None, aydioPath=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mainLayout.setSpacing(0)

        self.title = title
        self.boxID = boxID
        self.audio = audio
        self.sr = sr
        self.audioPath = aydioPath

        self.slaves = {}

        self.createTitleButton()
        self.createContentArea()

        self.mainLayout.addWidget(self.toggleButton)
        self.mainLayout.addWidget(self.contentArea)

        self.toggleButton.setText("▼ "+title)
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

        newSlaveButton = QPushButton("New slave")
        newSlaveButton.clicked.connect(self.showSlaveDialog)
        self.contentLayout.addWidget(newSlaveButton)

    def onToggled(self, checked):
        if checked:
            self.toggleButton.setText("► " + self.toggleButton.text()[2:])
            self.contentArea.setMaximumHeight(16777215)
            self.contentArea.setMinimumHeight(600)
        else:
            self.toggleButton.setText("▼ " + self.toggleButton.text()[2:])
            self.contentArea.setMaximumHeight(0)
            self.contentArea.setMinimumHeight(0)


    def showSlaveDialog(self):
        dialog = newSlaveDialog(self)
        dialog.slaveCreated.connect(self.addSlave)
        dialog.exec()
    def addSlave(self, slaveData, boxID=None):
        chooseBox = TagTypeChooseBox("Visible tags")
        manager = TagManager(chooseBox)
        wave = WaveWidget(self.audio, self.sr, manager, chooseBox, self.audioPath)
        if boxID is None:
            boxID = datetime.now().strftime("%Y%m%d%H%M%S%f")
        slave = SlaveBox(title=slaveData["name"], boxID=boxID, wave=wave, slavePin=slaveData["pin"])
        slave.boxDeleted.connect(self.deleteSlavesData)

        self.slaves[boxID] = slave
        self.contentLayout.addWidget(slave)

    def deleteSlavesData(self, boxID):
        print(self.slaves, boxID)
        if boxID in self.slaves:
            del self.slaves[boxID]
            return True
        return False
