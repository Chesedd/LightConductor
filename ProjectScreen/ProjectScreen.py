import os.path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QPushButton,
                            QFileDialog, QHBoxLayout,
                            QLabel, QDialog, QLineEdit)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QAction, QKeySequence
import librosa
from ProjectScreen.CollapsibleBox import CollapsibleBox
from ProjectScreen.WaveWidget import WaveWidget
from ProjectScreen.TagManager import TagManager
from ProjectScreen.ProjectManager import ProjectManager
from AssistanceTools.ChooseBox import  TagTypeChooseBox

from datetime import datetime

class newWaveWidgetDialog(QDialog):
    waveCreated = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.uiCreate()

    def uiCreate(self):
        waveNameText = QLabel("Название компонента")
        self.waveNameBar = QLineEdit()
        waveNameLayout = QHBoxLayout()
        waveNameLayout.addWidget(waveNameText)
        waveNameLayout.addWidget(self.waveNameBar)

        okButton = QPushButton("Ok")
        okButton.clicked.connect(self.onOkClicked)
        cancelButton = QPushButton("Cancel")
        cancelButton.clicked.connect(self.reject)
        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(okButton)
        buttonLayout.addWidget(cancelButton)

        self.mainScreen = QWidget()
        self.mainLayout = QVBoxLayout(self.mainScreen)
        self.mainLayout.addLayout(waveNameLayout)
        self.mainLayout.addLayout(buttonLayout)

        self.setLayout(self.mainLayout)

    def onOkClicked(self):
        waveTitle = self.waveNameBar.text()
        self.waveCreated.emit(waveTitle)
        self.accept()



class ProjectWindow(QMainWindow):
    def __init__(self, project_data):
        super().__init__()

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

        waveButton = QPushButton("Add wave")
        waveButton.clicked.connect(self.showWaveDialog)
        self.layout.addWidget(waveButton)

    def initExistingData(self):
        self.audio, self.sr = self.projectManager.loadAudioData()
        loadBoxes = self.projectManager.returnAllBoxes()
        for boxID in loadBoxes:
            box = loadBoxes[boxID]
            self.addWave(box["name"], box["id"])

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
            self.audio, self.sr = librosa.load(filePath, sr=None, mono=True)
        except Exception as e:
            print(e)
            return

    def showWaveDialog(self):
        dialog = newWaveWidgetDialog(self)
        dialog.waveCreated.connect(self.addWave)
        dialog.exec()

    def addWave(self, waveTitle, boxID=None):
        self.chooseBox = TagTypeChooseBox("Visible tags")
        self.manager = TagManager(self.chooseBox)
        self.wave = WaveWidget(self.audio, self.sr, self.manager, self.chooseBox)
        if boxID is None:
            boxID = datetime.now().strftime("%Y%m%d%H%M%S%f")
        box = CollapsibleBox(title=waveTitle, boxID=boxID, wave=self.wave)
        box.boxDeleted.connect(self.deleteBoxData)

        self.boxes[boxID] = box
        self.layout.addWidget(box)


    def deleteBoxData(self, boxID):
        print(self.boxes, boxID)
        if boxID in self.boxes:
            del self.boxes[boxID]
            return True
        return False

