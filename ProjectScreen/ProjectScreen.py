import logging

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                            QFileDialog, QMessageBox)
from PyQt6.QtCore import pyqtSignal, Qt, QUrl
from PyQt6.QtGui import QAction, QKeySequence
from ProjectScreen.PlateLogic.MasterBox import MasterBox
from ProjectScreen.ProjectManager import ProjectManager
from AssistanceTools.SimpleDialog import SimpleDialog
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from lightconductor.application.compiled_show import CompileShowsForMastersUseCase
from lightconductor.infrastructure.audio_loader import LibrosaAudioLoader
from lightconductor.infrastructure.legacy_mappers import LegacyMastersMapper
from lightconductor.infrastructure.legacy_project_storage import LegacyProjectStorage
from lightconductor.infrastructure.master_udp_upload_transport import MasterUdpUploadTransport
from lightconductor.presentation.project_controller import ProjectScreenController
from lightconductor.presentation.project_session_controller import ProjectSessionController

from datetime import datetime

logger = logging.getLogger(__name__)

#Диалог создания нового мастера
class newMasterDialog(SimpleDialog):
    masterCreated = pyqtSignal(dict)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.uiCreate()

    def uiCreate(self):
        self.mainLayout = QVBoxLayout(self)

        self.masterNameBar = self.LabelAndLine("Master's name")
        self.masterIpBar = self.LabelAndLine("Master IP")
        self.masterIpBar.setText("192.168.0.129")
        okButton = self.OkAndCancel()
        okButton.clicked.connect(self.onOkClicked)

    def onOkClicked(self):
        data = {
            "name": self.masterNameBar.text(),
            "ip": self.masterIpBar.text(),
        }
        self.masterCreated.emit(data)
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
            compile_use_case=CompileShowsForMastersUseCase(),
            transport=MasterUdpUploadTransport(port=43690, chunk_size=768),
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
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel(f"Project: {self.project_data['project_name']}")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.layout.addWidget(title)

        self.initButtons()

    #создание кнопок под юай
    def initButtons(self):
        controls = QWidget()
        controlsLayout = QHBoxLayout(controls)
        controlsLayout.setContentsMargins(0, 0, 0, 0)
        controlsLayout.setSpacing(8)

        addButton = QPushButton("Add track")
        addButton.clicked.connect(self.addTrack)
        controlsLayout.addWidget(addButton)

        waveButton = QPushButton("Add master")
        waveButton.clicked.connect(self.showMasterDialog)
        controlsLayout.addWidget(waveButton)

        uploadButton = QPushButton("Upload show")
        uploadButton.clicked.connect(self.uploadShow)
        controlsLayout.addWidget(uploadButton)

        showButton = QPushButton("Start show")
        showButton.clicked.connect(self.startShow)
        showButton.setStyleSheet(
            "QPushButton { background-color: #2d6a4f; border: 1px solid #3f8a68; font-weight: 600; }"
            "QPushButton:hover { background-color: #347a5a; }"
        )
        controlsLayout.addWidget(showButton)
        controlsLayout.addStretch(1)

        self.layout.addWidget(controls)

    def initExistingData(self):
        snapshot = self.sessionController.load_session()
        self.audio, self.sr, self.audioPath = snapshot.audio, snapshot.sample_rate, snapshot.audio_path
        masters = snapshot.boxes
        for masterID in masters:
            master = masters[masterID]
            slaves = master['slaves']
            self.addMaster(master["name"], master["id"], master.get("ip", "192.168.0.129"))
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
        slaveData["led_count"] = slave.get("led_count", 0)
        masterWidget.addSlave(slaveData, slave["id"])
        tagTypes = slave['tagTypes']
        manager = self.masters[master["id"]].slaves[slave["id"]].wave.manager
        return tagTypes, manager

    def initTypeAndTags(self, params, manager, wave):
        if "topology" not in params:
            rows = params.get("row", 1)
            cols = params.get("table", 1)
            params["topology"] = [i for i in range(rows * cols)]
        type = manager.addType(params)
        tags = []
        for tagID in params['tags']:
            tags.append(wave.addExistingTag(params['tags'][tagID], type))
        type.addExistingTags(tags)

    def saveData(self):
        logger.info("Saving project session")
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
            logger.warning("Audio file not found: %s", filePath)
            QMessageBox.warning(self, "Файл не найден", f"Файл не существует:\n{filePath}")
        except Exception as e:
            logger.exception("Failed to load audio track: %s", filePath)
            QMessageBox.critical(self, "Ошибка загрузки трека", str(e))
            return

    def showMasterDialog(self):
        dialog = newMasterDialog(self)
        dialog.masterCreated.connect(self.addMaster)
        dialog.exec()

    def addMaster(self, masterName, boxID=None, masterIp="192.168.0.129"):
        if isinstance(masterName, dict):
            masterIp = masterName.get("ip", masterIp)
            masterName = masterName.get("name", "")
        if boxID is None:
            boxID = datetime.now().strftime("%Y%m%d%H%M%S%f")
        master = MasterBox(title=masterName, boxID=boxID, audio=self.audio, sr=self.sr, aydioPath=self.audioPath, masterIp=masterIp)
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

    def uploadShow(self):
        try:
            self.showController.upload_show(self.masters)
            logger.info("Compiled show uploaded")
        except Exception as e:
            logger.exception("Failed to upload show")
            QMessageBox.critical(self, "Ошибка загрузки шоу", str(e))

    def startShow(self):
        if not hasattr(self, "audioPlayer"):
            logger.warning("Audio player not initialized, track required")
            QMessageBox.warning(self, "Нет трека", "Сначала добавьте аудио-трек.")
            return
        self.audioPlayer.setPosition(0)

        try:
            self.showController.send_start_signal(self.masters)
            logger.info("Start signal sent")
        except Exception as e:
            logger.exception("Failed to send start signal")
            QMessageBox.critical(self, "Ошибка старта шоу", str(e))
            return

        self.audioPlayer.play()
