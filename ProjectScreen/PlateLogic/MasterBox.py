import logging

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QPushButton,
    QMenu,
    QLabel,
    QHBoxLayout,
    QWidget,
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QThreadPool
from PyQt6.QtGui import QAction
from ProjectScreen.PlateLogic.SlaveBox import SlaveBox
from ProjectScreen.PlateLogic.MasterPingWorker import MasterPingWorker
from ProjectScreen.TagLogic.TagManager import TagManager
from datetime import datetime
from AssistanceTools.ChooseBox import  TagTypeChooseBox
from AssistanceTools.SimpleDialog import SimpleDialog
from ProjectScreen.TagLogic.WaveWidget import WaveWidget
from AssistanceTools.DropBox import DropBox
from lightconductor.application.commands import (
    AddSlaveCommand,
    DeleteSlaveCommand,
)
from lightconductor.application.duplicate import (
    build_duplicate_master_composite,
)
from lightconductor.application.device_templates import (
    build_apply_template_composite,
)
from lightconductor.application.host_reachability import PingStatus
from lightconductor.domain.models import Slave as DomainSlave

logger = logging.getLogger(__name__)

PING_INTERVAL_MS = 10000
PING_PORT = 43690
PING_TIMEOUT_S = 1.0

_INDICATOR_COLORS = {
    PingStatus.UNKNOWN.value: "#6a6a6a",
    PingStatus.ONLINE.value:  "#3a9f45",
    PingStatus.OFFLINE.value: "#c93434",
}

class newSlaveDialog(SimpleDialog):
    slaveCreated = pyqtSignal(dict)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.uiCreate()

    def uiCreate(self):
        self.mainLayout = QVBoxLayout(self)

        self.slaveNameBar = self.LabelAndLine("Slave's name")
        self.pinBar = self.LabelAndLine("Slave pin")
        self.ledCountBar = self.LabelAndLine("LED count")
        self.ledCountBar.setText("60")

        okButton = self.OkAndCancel()
        okButton.clicked.connect(self.onOkClicked)

    def onOkClicked(self):
        data = {}
        data["name"] = self.slaveNameBar.text()
        data["pin"] = self.pinBar.text()
        try:
            data["led_count"] = int(self.ledCountBar.text())
        except ValueError:
            data["led_count"] = 60
        self.slaveCreated.emit(data)
        self.accept()

class MasterBox(DropBox):
    def __init__(
        self,
        title="",
        parent=None,
        boxID='',
        audio=None,
        sr=None,
        aydioPath=None,
        masterIp="192.168.0.129",
        state=None,
        project_window=None,
        commands=None,
    ):
        super().__init__(parent)

        self.title = title
        self.boxID = boxID
        self.masterIp = masterIp
        self.audio = audio
        self.sr = sr
        self.audioPath = aydioPath
        self._state = state
        self._project_window = project_window
        self._commands = commands

        self.slaves = {}

        self.toggleButton.setText(f"▼ {title} (ip: {masterIp})")
        self._ping_status = PingStatus.UNKNOWN.value
        self._last_ping_at: str | None = None
        self._build_header_with_indicator()
        self._init_ping_timer()
        self.initSlaveButton()


    def _build_header_with_indicator(self):
        """Wrap toggleButton + status indicator in a header row. The
        base DropBox added toggleButton directly to its mainLayout; we
        detach, then re-add inside a new QWidget with a horizontal
        layout."""
        self.mainLayout.removeWidget(self.toggleButton)

        header = QWidget()
        headerLayout = QHBoxLayout(header)
        headerLayout.setContentsMargins(0, 0, 0, 0)
        headerLayout.setSpacing(8)
        headerLayout.addWidget(self.toggleButton, stretch=1)

        self.statusIndicator = QLabel()
        self.statusIndicator.setFixedSize(14, 14)
        self._apply_indicator_style()
        self.statusIndicator.setToolTip(
            "Status: unknown (no probe yet)",
        )
        headerLayout.addWidget(
            self.statusIndicator,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )

        self.mainLayout.insertWidget(0, header)

    def _apply_indicator_style(self):
        color = _INDICATOR_COLORS.get(
            self._ping_status,
            _INDICATOR_COLORS[PingStatus.UNKNOWN.value],
        )
        self.statusIndicator.setStyleSheet(
            f"QLabel {{"
            f" background-color: {color};"
            f" border: 1px solid #2e353d;"
            f" border-radius: 7px;"
            f"}}"
        )

    def _init_ping_timer(self):
        self._ping_timer = QTimer(self)
        self._ping_timer.setInterval(PING_INTERVAL_MS)
        self._ping_timer.timeout.connect(self._start_ping_probe)
        self._ping_timer.start()
        QTimer.singleShot(0, self._start_ping_probe)

    def _start_ping_probe(self):
        host = (self.masterIp or "").strip()
        worker = MasterPingWorker(
            master_id=self.boxID,
            host=host,
            port=PING_PORT,
            timeout=PING_TIMEOUT_S,
        )
        worker.signals.completed.connect(
            self._on_ping_completed,
            Qt.ConnectionType.QueuedConnection,
        )
        QThreadPool.globalInstance().start(worker)

    def _on_ping_completed(self, master_id: str, status: str):
        if master_id != self.boxID:
            return
        self._ping_status = status
        self._last_ping_at = datetime.now().strftime("%H:%M:%S")
        self._apply_indicator_style()
        self.statusIndicator.setToolTip(
            f"Status: {status} (last probed at "
            f"{self._last_ping_at})",
        )

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
        if boxID is None:
            boxID = datetime.now().strftime("%Y%m%d%H%M%S%f")
        manager = TagManager(
            chooseBox,
            state=self._state,
            project_window=self._project_window,
            master_id=self.boxID,
            slave_id=boxID,
            commands=self._commands,
        )
        wave = WaveWidget(
            self.audio,
            self.sr,
            manager,
            chooseBox,
            self.audioPath,
            state=self._state,
            project_window=self._project_window,
            master_id=self.boxID,
            slave_id=boxID,
            commands=self._commands,
        )
        slave = SlaveBox(
            title=slaveData["name"],
            boxID=boxID,
            wave=wave,
            slavePin=slaveData["pin"],
            ledCount=slaveData.get("led_count", 0),
            state=self._state,
            master_id=self.boxID,
            commands=self._commands,
            project_window=self._project_window,
        )
        slave.boxDeleted.connect(self.deleteSlavesData)

        self.slaves[boxID] = slave
        self.contentLayout.addWidget(slave)
        if (
            self._state is not None
            and self._project_window is not None
            and not self._project_window.is_loading()
        ):
            domain_slave = DomainSlave(
                id=boxID,
                name=slaveData["name"],
                pin=str(slaveData["pin"]),
                led_count=int(slaveData.get("led_count", 0) or 0),
            )
            if self._commands is not None:
                self._commands.push(
                    AddSlaveCommand(
                        master_id=self.boxID,
                        slave=domain_slave,
                    )
                )
            else:
                self._state.add_slave(self.boxID, domain_slave)

    def deleteSlavesData(self, boxID):
        logger.debug("Deleting slave boxID=%s, current slaves=%s", boxID, list(self.slaves.keys()))
        if boxID in self.slaves:
            del self.slaves[boxID]
            if (
                self._state is not None
                and self._project_window is not None
                and not self._project_window.is_loading()
            ):
                if self._commands is not None:
                    try:
                        self._commands.push(
                            DeleteSlaveCommand(
                                master_id=self.boxID,
                                slave_id=boxID,
                            )
                        )
                    except KeyError:
                        logger.warning(
                            "state missing slave %s on master %s during delete",
                            boxID, self.boxID,
                        )
                else:
                    try:
                        self._state.remove_slave(self.boxID, boxID)
                    except KeyError:
                        logger.warning(
                            "state missing slave %s on master %s during delete",
                            boxID, self.boxID,
                        )
            return True
        return False

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        duplicateAction = QAction("Duplicate master", self)
        duplicateAction.triggered.connect(self._on_duplicate_master)
        menu.addAction(duplicateAction)
        templates = self._available_templates()
        if templates:
            submenu = menu.addMenu("Add slave from template")
            for template in templates:
                name = template.get(
                    "template_name",
                ) or "(unnamed)"
                action = QAction(name, self)
                action.triggered.connect(
                    lambda _checked=False, tpl=template:
                        self._on_apply_template(tpl),
                )
                submenu.addAction(action)
        else:
            disabled = QAction(
                "Add slave from template (no templates)", self,
            )
            disabled.setEnabled(False)
            menu.addAction(disabled)
        menu.exec(event.globalPos())

    def _on_duplicate_master(self):
        if self._state is None or self._commands is None:
            return
        try:
            source = self._state.master(self.boxID)
        except KeyError:
            return
        existing_names = [
            m.name for m in self._state.masters().values()
        ]
        composite = build_duplicate_master_composite(
            source=source,
            existing_master_names=existing_names,
        )
        try:
            self._commands.push(composite)
        except Exception:
            logger.exception(
                "Duplicate master composite push failed",
            )

    def _available_templates(self):
        """Return the templates list from the project window's
        settings, or [] if settings is not reachable."""
        if self._project_window is None:
            return []
        settings = getattr(self._project_window, "settings", None)
        if settings is None:
            return []
        return list(settings.device_templates or [])

    def _on_apply_template(self, template: dict):
        if self._state is None or self._commands is None:
            return
        new_slave_id = datetime.now().strftime(
            "%Y%m%d%H%M%S%f",
        )
        try:
            composite = build_apply_template_composite(
                template=template,
                target_master_id=self.boxID,
                new_slave_id=new_slave_id,
            )
        except ValueError:
            logger.exception(
                "Template malformed; skipping apply",
            )
            return
        try:
            self._commands.push(composite)
        except Exception:
            logger.exception(
                "Apply template composite push failed",
            )
