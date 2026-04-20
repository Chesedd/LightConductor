import logging

from PyQt6.QtWidgets import QVBoxLayout, QPushButton, QMenu
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from ProjectScreen.PlateLogic.SlaveBox import SlaveBox
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
from lightconductor.domain.models import Slave as DomainSlave

logger = logging.getLogger(__name__)

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
