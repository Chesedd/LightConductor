import os.path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QPushButton,
                            QFileDialog, QHBoxLayout,
                            QLabel, QDialog, QLineEdit)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QAction, QKeySequence
import librosa
from ProjectScreen.SlaveBox import SlaveBox
from ProjectScreen.MasterBox import MasterBox
from ProjectScreen.WaveWidget import WaveWidget
from ProjectScreen.TagManager import TagManager
from ProjectScreen.ProjectManager import ProjectManager
from AssistanceTools.ChooseBox import  TagTypeChooseBox

from datetime import datetime

class newMasterDialog(QDialog):
    masterCreated = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.uiCreate()

    def uiCreate(self):
        masterNameText = QLabel("Master's name")
        self.masterNameBar = QLineEdit()
        masterNameLayout = QHBoxLayout()
        masterNameLayout.addWidget(masterNameText)
        masterNameLayout.addWidget(self.masterNameBar)

        okButton = QPushButton("Ok")
        okButton.clicked.connect(self.onOkClicked)
        cancelButton = QPushButton("Cancel")
        cancelButton.clicked.connect(self.reject)
        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(okButton)
        buttonLayout.addWidget(cancelButton)

        self.mainScreen = QWidget()
        self.mainLayout = QVBoxLayout(self.mainScreen)
        self.mainLayout.addLayout(masterNameLayout)
        self.mainLayout.addLayout(buttonLayout)

        self.setLayout(self.mainLayout)

    def onOkClicked(self):
        masterTitle = self.masterNameBar.text()
        self.masterCreated.emit(masterTitle)
        self.accept()



class ProjectWindow(QMainWindow):
    def __init__(self, project_data):
        super().__init__()
        self.masters = {}

        saveAction = QAction("Save", self)
        saveAction.setShortcut(QKeySequence("Ctrl+S"))
        saveAction.triggered.connect(self.saveData)
        self.addAction(saveAction)

        self.project_data = project_data
        self.audio = None
        self.sr = None
        self.boxCounter = 0
        self.projectManager = ProjectManager(self.project_data['project_name'])
        self.boxes = {}
        self.audioPath = None

        self.init_ui()
        self.initExistingData()


    def init_ui(self):
        self.setWindowTitle(self.project_data['project_name'])
        self.setGeometry(100, 100, 1400, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        addButton = QPushButton("Add track")
        addButton.clicked.connect(self.addTrack)
        self.layout.addWidget(addButton)

        waveButton = QPushButton("Add master")
        waveButton.clicked.connect(self.showMasterDialog)
        self.layout.addWidget(waveButton)

    def initExistingData(self):
        self.audio, self.sr, self.audioPath = self.projectManager.loadAudioData()
        loadBoxes = self.projectManager.returnAllBoxes()
        for boxID in loadBoxes:
            box = loadBoxes[boxID]
            tagTypes = box['tagTypes']
            self.addSlave(box["name"], box["id"])
            manager = self.boxes[box["id"]].wave.manager
            for tagType in tagTypes:
                params = tagTypes[tagType]
                params['name'] = tagType
                manager.addType(params)
                type = manager.types[params['name']]
                tags = []
                for tagID in params['tags']:
                    print(params['tags'][tagID])
                    tags.append(self.boxes[box["id"]].wave.addExistingTag(params['tags'][tagID], type))
                type.addExistingTags(tags)

    def saveData(self):
        print("Save")
        self.projectManager.saveAudioData(self.audio, self.sr)
        self.projectManager.saveData(self.boxes)

    def addTrack(self):
        filePath, _ = QFileDialog.getOpenFileName(
            self,
            "Choose audio",
            "",
            "Аудио файлы (*.mp3, *.wav, *.flac, *.ogg, *.m4a);;Все файлы (*)"
        )
        if not os.path.exists(filePath):
            print("File not exist")
            return
        try:
            self.audioPath = filePath
            self.audio, self.sr = librosa.load(filePath, sr=None, mono=True)
        except Exception as e:
            print(e)
            return

    def showMasterDialog(self):
        dialog = newMasterDialog(self)
        dialog.masterCreated.connect(self.addMaster)
        dialog.exec()

    def addMaster(self, masterName, boxID=None):
        if boxID is None:
            boxID = datetime.now().strftime("%Y%m%d%H%M%S%f")
        master = MasterBox(title=masterName, boxID=boxID, audio=self.audio, sr=self.sr, aydioPath=self.audioPath)
        self.masters[boxID] = master
        self.layout.addWidget(master)

    def addSlave(self, waveTitle, boxID=None):
        chooseBox = TagTypeChooseBox("Visible tags")
        manager = TagManager(chooseBox)
        wave = WaveWidget(self.audio, self.sr, manager, chooseBox, self.audioPath)
        if boxID is None:
            boxID = datetime.now().strftime("%Y%m%d%H%M%S%f")
        box = SlaveBox(title=waveTitle, boxID=boxID, wave=wave)
        box.boxDeleted.connect(self.deleteBoxData)

        self.boxes[boxID] = box
        self.layout.addWidget(box)


    def deleteBoxData(self, boxID):
        print(self.boxes, boxID)
        if boxID in self.boxes:
            del self.boxes[boxID]
            return True
        return False

