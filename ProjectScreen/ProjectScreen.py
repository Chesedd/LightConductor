from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QPushButton,
                            QFileDialog)
from PyQt6.QtCore import pyqtSignal, Qt, QUrl
from PyQt6.QtGui import QAction, QKeySequence
from ProjectScreen.PlateLogic.MasterBox import MasterBox
from ProjectScreen.ProjectManager import ProjectManager
from AssistanceTools.SimpleDialog import SimpleDialog
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from lightconductor.application.use_cases import BuildShowPayloadUseCase
from lightconductor.infrastructure.legacy_mappers import LegacyMastersMapper
from lightconductor.infrastructure.audio_loader import LibrosaAudioLoader
from lightconductor.infrastructure.udp_transport import UdpShowTransport, UdpTransportConfig
from lightconductor.infrastructure.legacy_project_storage import LegacyProjectStorage
from lightconductor.presentation.project_controller import ProjectScreenController
from lightconductor.presentation.project_session_controller import ProjectSessionController

from datetime import datetime

#Диалог создания нового мастера
class newMasterDialog(SimpleDialog):
    masterCreated = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.uiCreate()

    def uiCreate(self):
        self.mainLayout = QVBoxLayout(self)

        self.masterNameBar = self.LabelAndLine("Master's name")
        okButton = self.OkAndCancel()
        okButton.clicked.connect(self.onOkClicked)

    def onOkClicked(self):
        masterTitle = self.masterNameBar.text()
        self.masterCreated.emit(masterTitle)
        self.accept()



class ProjectWindow(QMainWindow):
    def __init__(self, project_data):
        super().__init__()
        self.masters = {}
        self.project_data = project_data
        self.audio = None
        self.sr = None
        self.boxCounter = 0
        self.projectManager = ProjectManager(self.project_data['project_name'])
        self.boxes = {}
        self.audioPath = None
        self.sessionController = ProjectSessionController(LegacyProjectStorage(self.projectManager))
        self.showController = ProjectScreenController(
            mapper=LegacyMastersMapper(),
            payload_use_case=BuildShowPayloadUseCase(),
            transport=UdpShowTransport(UdpTransportConfig(host="192.168.0.129", port=12345)),
            audio_loader=LibrosaAudioLoader(),
        )

        self.initActions()
        self.init_ui()
        self.initExistingData()
        self.initAudioPlayer()

    #создание действий под горячие клавиши
    def initActions(self):
        saveAction = QAction("Save", self)
        saveAction.setShortcut(QKeySequence("Ctrl+S"))
        saveAction.triggered.connect(self.saveData)
        self.addAction(saveAction)

    # создание аудио плеера
    def initAudioPlayer(self):
        if self.audio is not None:
            self.audioPlayer = QMediaPlayer()
            self.audioPlayer.setSource(QUrl.fromLocalFile(self.audioPath))
            self.audioOutput = QAudioOutput()
            self.audioPlayer.setAudioOutput(self.audioOutput)

    def init_ui(self):
        self.setWindowTitle(self.project_data['project_name'])
        self.setGeometry(100, 100, 1400, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.initButtons()

    #создание кнопок под юай
    def initButtons(self):
        addButton = QPushButton("Add track")
        addButton.clicked.connect(self.addTrack)
        self.layout.addWidget(addButton)

        waveButton = QPushButton("Add master")
        waveButton.clicked.connect(self.showMasterDialog)
        self.layout.addWidget(waveButton)

        loadButton = QPushButton("Load data")
        loadButton.clicked.connect(self.loadData)
        self.layout.addWidget(loadButton)

        showButton = QPushButton("Start show")
        showButton.clicked.connect(self.startShow)
        self.layout.addWidget(showButton)

    def initExistingData(self):
        snapshot = self.sessionController.load_session()
        self.audio, self.sr, self.audioPath = snapshot.audio, snapshot.sample_rate, snapshot.audio_path
        masters = snapshot.boxes
        for masterID in masters:
            master = masters[masterID]
            slaves = master['slaves']
            self.addMaster(master["name"], master["id"])
            masterWidget = self.masters[master["id"]]
            for slaveID in slaves:
                slave = slaves[slaveID]
                tagTypes, manager = self.initSlave(slave, masterWidget, master)
                wave = self.masters[master["id"]].slaves[slave["id"]].wave
                for tagType in tagTypes:
                    params = tagTypes[tagType]
                    params['name'] = tagType
                    self.initTypeAndTags(params, manager, wave)


    def initSlave(self, slave, masterWidget, master):
        slaveData = {}
        slaveData["name"] = slave["name"]
        slaveData["pin"] = slave["pin"]
        masterWidget.addSlave(slaveData, slave["id"])
        tagTypes = slave['tagTypes']
        manager = self.masters[master["id"]].slaves[slave["id"]].wave.manager
        return tagTypes, manager

    def initTypeAndTags(self, params, manager, wave):
        type = manager.addType(params)
        tags = []
        for tagID in params['tags']:
            tags.append(wave.addExistingTag(params['tags'][tagID], type))
        type.addExistingTags(tags)

    def saveData(self):
        print("Save")
        self.sessionController.save_session(self.audio, self.sr, self.masters)

    def addTrack(self):
        filePath, _ = QFileDialog.getOpenFileName(
            self,
            "Choose audio",
            "",
            "Аудио файлы (*.mp3, *.wav, *.flac, *.ogg, *.m4a);;Все файлы (*)"
        )
        if not filePath:
            return
        try:
            self.audio, self.sr, self.audioPath = self.showController.load_track(filePath)
            self.initAudioPlayer()
            self.updateSlavesAudio()
        except FileNotFoundError:
            print("File not exist")
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

    def updateSlavesAudio(self):
        for master in self.masters.values():
            master.audio = self.audio
            master.sr = self.sr
            master.audioPath = self.audioPath
            for slave in master.slaves.values():
                slave.wave.setAudioData(self.audio, self.sr, self.audioPath)
                slave.wave.clear()
                slave.wave.init_ui()

    def loadData(self):
        try:
            self.showController.send_show_payload(self.masters)
            print("Show payload sent")
        except Exception as e:
            print(f"Error sending payload: {e}")

    def startShow(self):
        if not hasattr(self, "audioPlayer"):
            print("Audio player is not initialized. Add a track first.")
            return
        self.audioPlayer.setPosition(0)

        try:
            self.showController.send_start_signal()
            print("Start signal sent")
        except Exception as e:
            print(f"Error sending broadcast: {e}")
        self.audioPlayer.play()
