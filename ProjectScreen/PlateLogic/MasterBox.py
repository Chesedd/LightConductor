import logging

from PyQt6.QtWidgets import QVBoxLayout, QPushButton
from PyQt6.QtCore import pyqtSignal
from ProjectScreen.PlateLogic.SlaveBox import SlaveBox
from ProjectScreen.TagLogic.TagManager import TagManager
from datetime import datetime
from AssistanceTools.ChooseBox import  TagTypeChooseBox
from AssistanceTools.SimpleDialog import SimpleDialog
from ProjectScreen.TagLogic.WaveWidget import WaveWidget
from AssistanceTools.DropBox import DropBox
from lightconductor.application.project_state import SlaveAdded, SlaveRemoved
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

        self.slaves = {}

        if self._state is not None:
            self._unsubscribe_state = self._state.subscribe(self._on_state_event)
        else:
            self._unsubscribe_state = None

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
        if boxID is None:
            boxID = datetime.now().strftime("%Y%m%d%H%M%S%f")
        if self._project_window is not None and self._project_window.is_loading():
            return
        if self._state is None:
            return
        master_domain = self._state.master(self.boxID)
        if boxID in master_domain.slaves:
            return
        self._state.add_slave(
            self.boxID,
            DomainSlave(
                id=boxID,
                name=slaveData["name"],
                pin=str(slaveData["pin"]),
                led_count=int(slaveData.get("led_count", 0) or 0),
            ),
        )

    def deleteSlavesData(self, boxID):
        logger.debug(
            "Deleting slave boxID=%s, current slaves=%s",
            boxID, list(self.slaves.keys()),
        )
        if boxID not in self.slaves:
            return False
        if (
            self._state is not None
            and self._project_window is not None
            and not self._project_window.is_loading()
        ):
            try:
                self._state.remove_slave(self.boxID, boxID)
            except KeyError:
                logger.warning(
                    "state missing slave %s on master %s during delete",
                    boxID, self.boxID,
                )
            return True
        # Headless / no-state fallback.
        del self.slaves[boxID]
        return True

    def _on_state_event(self, event):
        if getattr(event, "master_id", None) != self.boxID:
            return
        if isinstance(event, SlaveAdded):
            self._handle_slave_added(event)
        elif isinstance(event, SlaveRemoved):
            self._handle_slave_removed(event)

    def _handle_slave_added(self, event):
        if event.slave_id in self.slaves:
            return
        slave_domain = self._state.master(self.boxID).slaves[event.slave_id]
        self._build_slave_widget_from_state(slave_domain)

    def _handle_slave_removed(self, event):
        slave_widget = self.slaves.pop(event.slave_id, None)
        if slave_widget is not None:
            slave_widget.deleteLater()

    def _build_slave_widget_from_state(self, slave_domain):
        """Build SlaveBox + TagManager + WaveWidget from a domain Slave.

        StateReplaced does not re-emit descendant events, so for tag_types
        and tags already present on the domain slave we drive the same
        code paths the listeners use (via TagManager.addType with
        is_loading() == True, and WaveWidget.addExistingTag)."""
        chooseBox = TagTypeChooseBox("Visible tags")
        manager = TagManager(
            chooseBox,
            state=self._state,
            project_window=self._project_window,
            master_id=self.boxID,
            slave_id=slave_domain.id,
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
            slave_id=slave_domain.id,
        )
        slave_widget = SlaveBox(
            title=slave_domain.name,
            boxID=slave_domain.id,
            wave=wave,
            slavePin=slave_domain.pin,
            ledCount=slave_domain.led_count,
            state=self._state,
            master_id=self.boxID,
        )
        slave_widget.boxDeleted.connect(self.deleteSlavesData)
        self.slaves[slave_domain.id] = slave_widget
        self.contentLayout.addWidget(slave_widget)

        for type_name, tag_type in slave_domain.tag_types.items():
            params = {
                "name": tag_type.name,
                "color": tag_type.color,
                "pin": tag_type.pin,
                "row": int(tag_type.rows),
                "table": int(tag_type.columns),
                "topology": list(tag_type.topology),
            }
            widget_type = manager.addType(params)
            for domain_tag in tag_type.tags:
                tag_dict = {
                    "time": domain_tag.time_seconds,
                    "action": domain_tag.action,
                    "colors": domain_tag.colors,
                }
                wave.addExistingTag(tag_dict, widget_type)

        return slave_widget
