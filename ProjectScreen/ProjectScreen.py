import os.path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QPushButton,
                            QFileDialog, QHBoxLayout,
                            QLabel, QDialog, QLineEdit)
from PyQt6.QtCore import pyqtSignal, Qt
import librosa
from ProjectScreen.CollapsibleBox import CollapsibleBox
from ProjectScreen.WaveWidget import WaveWidget
from ProjectScreen.TagManager import TagManager
from AssistanceTools.ChooseBox import  TagTypeChooseBox
from AssistanceTools.TagState import TagState

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
        self.project_data = project_data
        self.audio = None
        self.sr = None
        self.boxCounter = 0

        self.init_ui()


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

    def addWave(self, waveTitle):
        box = CollapsibleBox(waveTitle)
        self.chooseBox = TagTypeChooseBox("Visible tags")
        self.manager = TagManager(self.chooseBox)
        self.manager.newTypeCreate.connect(self.addTagState)
        self.wave = WaveWidget(self.audio, self.sr, self.manager, self.chooseBox)

        addButton = QPushButton("Add tag")
        addButton.clicked.connect(self.wave.addTag)
        waveButtons = QWidget()
        waveButtons.layout = QVBoxLayout(waveButtons)
        waveButtons.layout.addWidget(self.chooseBox)
        waveButtons.layout.addWidget(addButton)

        waveSpace = QWidget()
        waveSpace.layout = QHBoxLayout(waveSpace)
        waveSpace.layout.addWidget(waveButtons)
        waveSpace.layout.addWidget(self.wave)

        tagsWidget = QWidget()
        self.tagsLayout = QHBoxLayout()
        tagsWidget.setLayout(self.tagsLayout)

        centralWidget = QWidget()
        centralWidget.layout = QVBoxLayout(centralWidget)
        centralWidget.layout.addWidget(waveSpace)
        centralWidget.layout.addWidget(tagsWidget)

        mainWidget = QWidget()
        mainWidget.layout = QHBoxLayout(mainWidget)
        mainWidget.layout.addWidget(centralWidget)
        mainWidget.layout.addWidget(self.manager)

        box.addWidget(mainWidget)
        self.layout.addWidget(box)

    def addTagState(self, tagType):
        self.tagsLayout.addWidget(TagState(tagType))
