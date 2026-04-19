import pyqtgraph as pg

from PyQt6.QtGui import QColor
from PyQt6.QtCore import QPointF, Qt, pyqtSignal

from ProjectScreen.TagLogic.TagObject import Tag
from ProjectScreen.TagLogic.WaveRenderer import WaveRenderer


class WaveWidget(pg.PlotWidget):
    positionUpdate = pyqtSignal(float, str)
    def __init__(self, audioData, sr, manager, chooseBox, audioPath):
        super().__init__()
        self.manager = manager
        self.chooseBox = chooseBox
        self.chooseBox.stateChanged.connect(self.editTagTypeOnWave)
        self.vb = self.getViewBox()
        self._renderer = WaveRenderer(
            plot_widget=self,
            audioData=audioData,
            sr=sr,
            audioPath=audioPath,
        )
        self._renderer.init_ui()
        self._renderer.setupMouse()

    def setAudioData(self, audioData, sr, audioPath):
        self._renderer.setAudioData(audioData, sr, audioPath)

    def init_ui(self):
        self._renderer.init_ui()

    def keyPressEvent(self, ev):
        step = 0.1
        if ev.key() == Qt.Key.Key_Right:
            self._renderer.audioPlayer.setPosition(
                round((self._renderer.selectedLine.value() + step) * 1000))
        elif ev.key() == Qt.Key.Key_Left:
            self._renderer.audioPlayer.setPosition(
                round((self._renderer.selectedLine.value() - step) * 1000))

    def addTag(self, data):
        self.addTagAtTime(data, self._renderer.selectedLine.pos().x())

    def addTagAtTime(self, data, time):
        color = self.manager.curType.color
        r, g, b = map(int, color.split(','))
        tag = Tag(
            pos=QPointF(time, 0.0),
            angle=90,
            pen=pg.mkPen(QColor(r, g, b), width=3),
            action=data["action"],
            colors=data["colors"],
            type=self.manager.curType,
            manager=self.manager,
        )
        self.addItem(tag)
        self.manager.curType.addTag(tag)

    def addExistingTag(self, data, type):
        color = type.color
        r, g, b = map(int, color.split(','))
        tag = Tag(pos=QPointF(data["time"], 0.0), angle=90, pen=pg.mkPen(QColor(r, g, b), width=3), action=data["action"], colors=data["colors"], type = type, manager = self.manager)
        self.addItem(tag)
        type.addTag(tag)
        return tag

    def editTagTypeOnWave(self, data):
        tags = self.manager.types[data["tagType"]].tags
        for tag in tags:
            if data["state"]:
                tag.show()
            else:
                tag.hide()

    def playOrPause(self, action):
        self._renderer.playOrPause(action)

    def playAndPause(self):
        self._renderer.playAndPause()
