from PyQt6.QtWidgets import QVBoxLayout, QPushButton
from PyQt6.QtCore import pyqtSignal
from ProjectScreen.PlateLogic.SlaveBox import SlaveBox
from ProjectScreen.TagLogic.TagManager import TagManager
from datetime import datetime
from AssistanceTools.ChooseBox import  TagTypeChooseBox
from AssistanceTools.SimpleDialog import SimpleDialog
from ProjectScreen.TagLogic.WaveWidget import WaveWidget
from AssistanceTools.DropBox import DropBox

class newSlaveDialog(SimpleDialog):
    slaveCreated = pyqtSignal(dict)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.uiCreate()

    def uiCreate(self):
        self.mainLayout = QVBoxLayout(self)

        self.slaveNameBar = self.LabelAndLine("Slave's name")
        self.pinBar = self.LabelAndLine("Slave pin")

        okButton = self.OkAndCancel()
        okButton.clicked.connect(self.onOkClicked)

    def onOkClicked(self):
        data = {}
        data["name"] = self.slaveNameBar.text()
        data["pin"] = self.pinBar.text()
        self.slaveCreated.emit(data)
        self.accept()

class MasterBox(DropBox):
    def __init__(self, title="", parent=None, boxID='', audio=None, sr=None, aydioPath=None):
        super().__init__(parent)

        self.title = title
        self.boxID = boxID
        self.audio = audio
        self.sr = sr
        self.audioPath = aydioPath

        self.slaves = {}

        self.toggleButton.setText("▼ "+title)
        self.initSlaveButton()


    def initSlaveButton(self):
        newSlaveButton = QPushButton("New slave")
        newSlaveButton.clicked.connect(self.showSlaveDialog)
        self.contentLayout.addWidget(newSlaveButton)

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
