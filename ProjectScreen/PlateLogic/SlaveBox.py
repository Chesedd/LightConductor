from PyQt6.QtWidgets import (
    QLabel, QHBoxLayout, QVBoxLayout, QPushButton,
    QWidget, QMenu)
from PyQt6.QtGui import QAction

from AssistanceTools.TagState import TagState
from ProjectScreen.TagLogic.TagScreen import TagInfoScreen
from AssistanceTools.FlowLayout import FlowLayout
from AssistanceTools.DropBox import DropBox
import bisect

from ProjectScreen.PlateLogic.TagDialog import TagDialog
from ProjectScreen.PlateLogic.TagGroupPatternDialog import TagGroupPatternDialog
from ProjectScreen.PlateLogic.RenameDialog import RenameDialog
from ProjectScreen.PlateLogic.DeleteDialog import DeleteDialog


class SlaveBox(DropBox):
    def __init__(self, title="", parent=None, boxID='', wave=None, slavePin = '', ledCount=0):
        super().__init__(parent)

        self.slavePin = slavePin
        self.ledCount = ledCount

        self.title = title
        self.boxID = boxID

        self.wave = wave
        self.wave.manager.box = self

        self.toggleButton.setText(f"▼ {title} (pin: {slavePin}, leds: {ledCount})")

        self.initUI()

    def initUI(self):
        self.wave.positionUpdate.connect(self.onPositionUpdate)
        self.wave.manager.newTypeCreate.connect(self.addTagState)

        waveWidget = QWidget()
        waveWidget.layout = QVBoxLayout(waveWidget)
        waveWidget.layout.addWidget(self.initWaveButtons())
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

        self.tagInfo = TagInfoScreen(tagTypes=self.wave.manager.types)
        self.wave.manager.tagScreen = self.tagInfo

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
        dialog = TagDialog(curType.row, curType.table, curType.topology, self)
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
            tags = widget.tagType.tags
            times = [tag.time for tag in tags]
            pos = bisect.bisect_right(times, time) - 1
            if pos >= 0:
                tag = tags[pos]
                widget.changeState(tag.action)
            else:
                widget.changeState(False)
        self.timeLabel.setText(timeStr)

    def contextMenuEvent(self, a0):
        menu = QMenu(self)

        renameAction = QAction("Rename", self)
        renameAction.triggered.connect(self.showRenameDialog)
        menu.addAction(renameAction)

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

