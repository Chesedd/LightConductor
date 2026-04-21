import bisect

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from AssistanceTools.DropBox import DropBox
from AssistanceTools.FlowLayout import FlowLayout
from AssistanceTools.TagState import TagState
from lightconductor.application.device_templates import (
    template_from_slave,
)
from lightconductor.application.duplicate import (
    build_duplicate_slave_composite,
)
from lightconductor.config import save_settings
from ProjectScreen.PlateLogic.DeleteDialog import DeleteDialog
from ProjectScreen.PlateLogic.RenameDialog import RenameDialog
from ProjectScreen.PlateLogic.TagDialog import TagDialog
from ProjectScreen.PlateLogic.TagGroupPatternDialog import TagGroupPatternDialog
from ProjectScreen.TagLogic.TagScreen import TagInfoScreen
from ProjectScreen.TagLogic.WaveMiniMap import WaveMiniMap


class SlaveBox(DropBox):
    def __init__(
        self,
        title="",
        parent=None,
        boxID="",
        wave=None,
        slavePin="",
        ledCount=0,
        gridRows=1,
        gridColumns=0,
        ledCells=None,
        state=None,
        master_id=None,
        commands=None,
        project_window=None,
    ):
        super().__init__(parent)

        self.slavePin = slavePin
        self.ledCount = ledCount
        self._grid_rows = int(gridRows or 1)
        self._grid_columns = int(gridColumns or 0)
        self._led_cells = list(ledCells or [])

        self.title = title
        self.boxID = boxID

        self.wave = wave
        self.wave.manager.box = self

        self._state = state
        self._master_id = master_id
        self._commands = commands
        self._project_window = project_window

        self.toggleButton.setText(f"▼ {title} (pin: {slavePin}, leds: {ledCount})")

        self.initUI()

    def initUI(self):
        self.wave.positionUpdate.connect(self.onPositionUpdate)
        self.wave.manager.newTypeCreate.connect(self.addTagState)

        waveWidget = QWidget()
        waveWidget.layout = QVBoxLayout(waveWidget)
        waveWidget.layout.addWidget(self.initWaveButtons())
        self.miniMap = WaveMiniMap(
            target_wave=self.wave,
            audioData=self.wave._renderer.audioData,
            sr=self.wave._renderer.sr,
            duration=self.wave._renderer.duration,
        )
        self.miniMap.setData(
            audioData=self.wave._renderer.audioData,
            sr=self.wave._renderer.sr,
            duration=self.wave._renderer.duration,
        )
        waveWidget.layout.addWidget(self.miniMap)
        waveWidget.layout.addWidget(self.wave)

        waveSpace = QWidget()
        waveSpace.layout = QHBoxLayout(waveSpace)
        waveSpace.layout.addWidget(self.initTagWaveButtons())
        waveSpace.layout.addWidget(waveWidget)

        tagsWidget = QWidget()
        self.tagsLayout = FlowLayout()
        tagsWidget.setLayout(self.tagsLayout)

        centralWidget = QWidget()
        centralWidget.layout = QVBoxLayout(centralWidget)
        centralWidget.layout.addWidget(waveSpace)
        centralWidget.layout.addWidget(tagsWidget)

        self.tagInfo = TagInfoScreen(
            state=self._state,
            master_id=self._master_id,
            slave_id=self.boxID,
            wave=self.wave,
            commands=self._commands,
        )
        self.wave.manager.tagScreen = self.tagInfo
        self.wave.waveActivated.connect(self._on_wave_activated)

        self.mainWidget = QWidget()
        self.mainLayout = QHBoxLayout(self.mainWidget)
        self.mainLayout.addWidget(centralWidget, 3)
        self.mainLayout.addWidget(self.wave.manager, 2)
        self.mainLayout.addWidget(self.tagInfo, 1)

        self.addWidget(self.mainWidget)

    def initTagWaveButtons(self):
        addButton = QPushButton("Add tag")
        addButton.clicked.connect(self.createTag)
        addGroupButton = QPushButton("Add tag group")
        addGroupButton.clicked.connect(self.createTagGroup)
        tagWaveButtons = QWidget()
        tagWaveButtons.layout = QVBoxLayout(tagWaveButtons)
        tagWaveButtons.layout.addWidget(self.wave.chooseBox)
        tagWaveButtons.layout.addWidget(addButton)
        tagWaveButtons.layout.addWidget(addGroupButton)

        return tagWaveButtons

    def initWaveButtons(self):
        waveButtons = QWidget()
        waveButtons.layout = QHBoxLayout(waveButtons)
        self.playButton = QPushButton("Play")
        self.playButton.clicked.connect(self.playOrPause)
        self.playAndPauseButton = QPushButton("Play+Pause")
        self.playAndPauseButton.clicked.connect(self.wave.playAndPause)
        self.timeLabel = QLabel("time")
        waveButtons.layout.addWidget(self.playButton)
        waveButtons.layout.addWidget(self.playAndPauseButton)
        waveButtons.layout.addWidget(self.timeLabel)

        return waveButtons

    def _on_wave_activated(self):
        if self._project_window is not None:
            self._project_window.set_active_slave(self)

    def playOrPause(self):
        state = self.playButton.text()
        if state == "Play":
            self.playButton.setText("Pause")
        else:
            self.playButton.setText("Play")
        self.wave.playOrPause(state)

    def addTagState(self, tagType):
        state = TagState(tagType)
        self.tagsLayout.addWidget(state)

    def createTag(self):
        curType = self.wave.manager.curType
        if curType is None:
            return
        slave = None
        if self._state is not None and self._master_id is not None:
            try:
                slave = self._state.master(self._master_id).slaves[self.boxID]
            except KeyError:
                slave = None
        current_time = 0.0
        try:
            current_time = float(self.wave._renderer.selectedLine.value())
        except Exception:
            current_time = 0.0
        led_count = int(getattr(slave, "led_count", 0) or 0) if slave else 0
        settings = None
        on_presets_changed = None
        if self._project_window is not None:
            settings = getattr(self._project_window, "settings", None)
            on_presets_changed = getattr(
                self._project_window,
                "update_color_presets",
                None,
            )
        slave_grid_columns = int(getattr(slave, "grid_columns", 0) or 0) if slave else 0
        dialog = TagDialog(
            curType.row,
            curType.table,
            curType.topology,
            self,
            slave=slave,
            type_name=curType.name,
            current_time=current_time,
            led_count=led_count,
            settings=settings,
            on_presets_changed=on_presets_changed,
            slave_grid_columns=slave_grid_columns,
        )
        dialog.tagCreated.connect(self.wave.addTag)
        dialog.exec()

    def createTagGroup(self):
        curType = self.wave.manager.curType
        if curType is None:
            return
        led_count = len(curType.topology)
        dialog = TagGroupPatternDialog(led_count=led_count, parent=self)
        if dialog.exec():
            for tag_data in dialog.buildTags():
                self.wave.addTagAtTime(
                    {
                        "action": tag_data["action"],
                        "colors": tag_data["colors"],
                    },
                    tag_data["time"],
                )

    def onPositionUpdate(self, time, timeStr):
        for i in range(self.tagsLayout.count()):
            widget = self.tagsLayout.itemAt(i).widget()
            type_name = widget.tagType.name
            domain_tags = []
            if self._state is not None and self._master_id is not None:
                try:
                    domain_tags = (
                        self._state.master(self._master_id)
                        .slaves[self.boxID]
                        .tag_types[type_name]
                        .tags
                    )
                except KeyError:
                    domain_tags = []
            times = [t.time_seconds for t in domain_tags]
            pos = bisect.bisect_right(times, time) - 1
            if pos >= 0:
                tag = domain_tags[pos]
                widget.changeState(tag.action)
            else:
                widget.changeState(False)
        self.timeLabel.setText(timeStr)

    def contextMenuEvent(self, a0):
        menu = QMenu(self)

        renameAction = QAction("Rename", self)
        renameAction.triggered.connect(self.showRenameDialog)
        menu.addAction(renameAction)

        duplicateAction = QAction("Duplicate slave", self)
        duplicateAction.triggered.connect(self._on_duplicate_slave)
        menu.addAction(duplicateAction)

        saveTemplateAction = QAction("Save as template", self)
        saveTemplateAction.triggered.connect(
            self._on_save_as_template,
        )
        menu.addAction(saveTemplateAction)

        deleteAction = QAction("Delete", self)
        deleteAction.triggered.connect(self.showDeleteDialog)
        menu.addAction(deleteAction)

        menu.exec(a0.globalPos())

    def addWidget(self, widget):
        self.contentLayout.addWidget(widget)

    def removeWidget(self, widget):
        self.contentLayout.removeWidget(widget)
        widget.setParent(None)

    def clear(self):
        while self.contentLayout.count():
            child = self.contentLayout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def showRenameDialog(self):
        dialog = RenameDialog(self)
        dialog.boxRenamed.connect(self.renameBox)
        dialog.exec()

    def renameBox(self, newTitle):
        self.toggleButton.setText("▼ " + newTitle)

    def showDeleteDialog(self):
        dialog = DeleteDialog(self)
        dialog.boxDelete.connect(self.deleteBox)
        dialog.exec()

    def deleteBox(self):
        self.boxDeleted.emit(self.boxID)
        self.deleteLater()

    def _on_duplicate_slave(self):
        if self._state is None or self._commands is None:
            return
        if self._master_id is None:
            return
        try:
            master = self._state.master(self._master_id)
            source = master.slaves[self.boxID]
        except KeyError:
            return
        existing_names = [s.name for s in master.slaves.values()]
        composite = build_duplicate_slave_composite(
            source=source,
            target_master_id=self._master_id,
            existing_slave_names=existing_names,
        )
        try:
            self._commands.push(composite)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Duplicate slave composite push failed",
            )

    def _on_save_as_template(self):
        if self._state is None:
            return
        if self._master_id is None:
            return
        project_window = self._project_window
        if project_window is None:
            return
        settings = getattr(project_window, "settings", None)
        if settings is None:
            return
        try:
            source = self._state.master(self._master_id).slaves[self.boxID]
        except KeyError:
            return
        from PyQt6.QtWidgets import (
            QDialog,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMessageBox,
            QPushButton,
            QVBoxLayout,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("Save as template")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Template name:"))
        name_edit = QLineEdit(source.name)
        name_edit.selectAll()
        layout.addWidget(name_edit)
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        template_name = name_edit.text().strip()
        if not template_name:
            QMessageBox.warning(
                self,
                "Invalid name",
                "Template name cannot be empty.",
            )
            return
        template = template_from_slave(source, template_name)
        existing = list(settings.device_templates or [])
        existing.append(template)
        settings.device_templates = existing
        try:
            save_settings(settings)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "failed to persist device template",
            )
            QMessageBox.warning(
                self,
                "Save failed",
                "Template saved in memory but could not be persisted to settings.json.",
            )
