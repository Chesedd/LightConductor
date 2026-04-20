import logging

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                            QFileDialog, QMessageBox)
from PyQt6.QtCore import pyqtSignal, Qt, QUrl
from PyQt6.QtGui import QAction, QKeySequence
from ProjectScreen.PlateLogic.MasterBox import MasterBox
from AssistanceTools.SimpleDialog import SimpleDialog
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from lightconductor.application.compiled_show import CompileShowsForMastersUseCase
from lightconductor.application.project_state import (
    MasterAdded,
    MasterRemoved,
    ProjectState,
    StateReplaced,
)
from lightconductor.application.validation_service import (
    SEVERITY_ERROR,
    ValidationIssue,
    ValidationService,
)
from lightconductor.config import AppSettings, load_settings
from lightconductor.domain.models import Master as DomainMaster
from lightconductor.infrastructure.audio_loader import LibrosaAudioLoader
from lightconductor.infrastructure.master_udp_upload_transport import MasterUdpUploadTransport
from lightconductor.infrastructure.project_session_storage import ProjectSessionStorage
from lightconductor.infrastructure.ui_session_bridge import UiSessionBridge
from lightconductor.presentation.project_controller import ProjectScreenController
from lightconductor.presentation.project_session_controller import ProjectSessionController

from datetime import datetime

logger = logging.getLogger(__name__)

#Диалог создания нового мастера
class newMasterDialog(SimpleDialog):
    masterCreated = pyqtSignal(dict)
    def __init__(self, default_ip: str, parent=None):
        super().__init__(parent)
        self._default_ip = default_ip
        self.uiCreate()

    def uiCreate(self):
        self.mainLayout = QVBoxLayout(self)

        self.masterNameBar = self.LabelAndLine("Master's name")
        self.masterIpBar = self.LabelAndLine("Master IP")
        self.masterIpBar.setText(self._default_ip)
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
        self.settings = load_settings()
        self.masters = {}
        self.project_data = project_data
        self.audio = None
        self.sr = None
        self.boxCounter = 0
        self.boxes = {}
        self.audioPath = None
        self.sessionController = ProjectSessionController(
            UiSessionBridge(
                domain_storage=ProjectSessionStorage(),
                project_name=self.project_data['project_name'],
            )
        )
        self.showController = ProjectScreenController(
            compile_use_case=CompileShowsForMastersUseCase(),
            transport=MasterUdpUploadTransport(
                port=self.settings.udp_port,
                chunk_size=self.settings.udp_chunk_size,
            ),
            audio_loader=LibrosaAudioLoader(),
        )
        self.validation_service = ValidationService()
        self.state = ProjectState()
        self._building_widgets_from_state = False
        self._unsubscribe_state = self.state.subscribe(self._on_state_event)

        self.initActions()
        self.init_ui()
        self.initExistingData()
        self.initAudioPlayer()

    def is_loading(self) -> bool:
        return self._building_widgets_from_state

    #создание действий под горячие клавиши
    def initActions(self):
        saveAction = QAction("Save", self)
        saveAction.setShortcut(QKeySequence("Ctrl+S"))
        saveAction.triggered.connect(self.saveData)
        self.addAction(saveAction)

    def _report_validation_errors(
        self,
        issues: list[ValidationIssue],
        operation_name: str,
    ) -> bool:
        """Show a QMessageBox listing validation errors.
        Returns True if operation should proceed, False if blocked.

        Warnings are NOT shown in a blocking dialog — they are
        logged only. Errors block and are displayed.
        """
        errors = [i for i in issues if i.severity == SEVERITY_ERROR]
        warnings_ = [i for i in issues if i.severity != SEVERITY_ERROR]

        for warning in warnings_:
            logger.warning(
                "Validation warning during %s: [%s] %s — %s",
                operation_name, warning.category, warning.path,
                warning.message,
            )

        if not errors:
            return True

        lines = [
            f"• [{issue.category}] {issue.path}\n  {issue.message}"
            for issue in errors
        ]
        QMessageBox.warning(
            self,
            f"{operation_name} blocked",
            "Project has validation errors:\n\n" + "\n\n".join(lines),
        )
        return False

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
        self.audio = snapshot.audio
        self.sr = snapshot.sample_rate
        self.audioPath = snapshot.audio_path
        self.state.load_masters(snapshot.masters)

    def _on_state_event(self, event):
        if isinstance(event, StateReplaced):
            self._rebuild_all_from_state()
        elif isinstance(event, MasterAdded):
            self._handle_master_added(event)
        elif isinstance(event, MasterRemoved):
            self._handle_master_removed(event)

    def _rebuild_all_from_state(self):
        self._building_widgets_from_state = True
        try:
            for master_id, master in self.state.masters().items():
                master_widget = self._build_master_widget(master)
                for slave_id, slave in master.slaves.items():
                    master_widget._build_slave_widget_from_state(slave)
        finally:
            self._building_widgets_from_state = False

    def _handle_master_added(self, event):
        if event.master_id in self.masters:
            return
        domain_master = self.state.master(event.master_id)
        self._build_master_widget(domain_master)

    def _handle_master_removed(self, event):
        master_widget = self.masters.pop(event.master_id, None)
        if master_widget is not None:
            master_widget.deleteLater()

    def _build_master_widget(self, domain_master) -> MasterBox:
        master = MasterBox(
            title=domain_master.name,
            boxID=domain_master.id,
            audio=self.audio,
            sr=self.sr,
            aydioPath=self.audioPath,
            masterIp=domain_master.ip,
            state=self.state,
            project_window=self,
        )
        self.masters[domain_master.id] = master
        self.layout.addWidget(master)
        return master

    def saveData(self):
        logger.info("Save requested")
        domain_masters = self.state.masters()
        issues = self.validation_service.validate(domain_masters)
        if not self._report_validation_errors(issues, "Save"):
            return
        self.sessionController.save_session(
            self.audio, self.sr, domain_masters,
        )

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
        dialog = newMasterDialog(self.settings.default_master_ip, self)
        dialog.masterCreated.connect(self.addMaster)
        dialog.exec()

    def addMaster(self, masterName, boxID=None, masterIp=None):
        if isinstance(masterName, dict):
            masterIp = masterName.get("ip", masterIp)
            masterName = masterName.get("name", "")
        if masterIp is None:
            masterIp = self.settings.default_master_ip
        if boxID is None:
            boxID = datetime.now().strftime("%Y%m%d%H%M%S%f")
        if self._building_widgets_from_state:
            return
        if self.state.has_master(boxID):
            return
        self.state.add_master(
            DomainMaster(id=boxID, name=masterName, ip=masterIp)
        )

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
            domain_masters = self.state.masters()
            issues = self.validation_service.validate(domain_masters)
            if not self._report_validation_errors(issues, "Upload"):
                return
            self.showController.upload_show(domain_masters)
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
            self.showController.send_start_signal(self.state.masters())
            logger.info("Start signal sent")
        except Exception as e:
            logger.exception("Failed to send start signal")
            QMessageBox.critical(self, "Ошибка старта шоу", str(e))
            return

        self.audioPlayer.play()
