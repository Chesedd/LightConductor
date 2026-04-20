import pyqtgraph as pg

from PyQt6.QtCore import Qt, pyqtSignal

from ProjectScreen.TagLogic.WaveRenderer import WaveRenderer
from ProjectScreen.TagLogic.TagTimelineController import TagTimelineController


class WaveWidget(pg.PlotWidget):
    positionUpdate = pyqtSignal(float, str)
    waveActivated = pyqtSignal()
    def __init__(
        self,
        audioData,
        sr,
        manager,
        chooseBox,
        audioPath,
        state=None,
        project_window=None,
        master_id=None,
        slave_id=None,
        commands=None,
    ):
        super().__init__()
        self.manager = manager
        self.chooseBox = chooseBox
        self.vb = self.getViewBox()
        self.scene().sigMouseClicked.connect(
            lambda ev: self.waveActivated.emit()
        )
        self._renderer = WaveRenderer(
            plot_widget=self,
            audioData=audioData,
            sr=sr,
            audioPath=audioPath,
        )
        self._tagController = TagTimelineController(
            plot_widget=self,
            manager=manager,
            renderer=self._renderer,
            state=state,
            project_window=project_window,
            master_id=master_id,
            slave_id=slave_id,
            commands=commands,
        )
        self.chooseBox.stateChanged.connect(self.editTagTypeOnWave)
        self._renderer.init_ui()
        self._renderer.setupMouse()
        self._tagController.install_rubber_band()

    def setAudioData(self, audioData, sr, audioPath):
        self._renderer.setAudioData(audioData, sr, audioPath)

    def init_ui(self):
        self._renderer.init_ui()

    def keyPressEvent(self, ev):
        modifiers = ev.modifiers()
        step = 1.0 if modifiers & Qt.KeyboardModifier.ShiftModifier else 0.1
        if ev.key() == Qt.Key.Key_Right:
            self._renderer.audioPlayer.setPosition(
                round((self._renderer.selectedLine.value() + step) * 1000))
        elif ev.key() == Qt.Key.Key_Left:
            self._renderer.audioPlayer.setPosition(
                round((self._renderer.selectedLine.value() - step) * 1000))

    def addTag(self, data):
        self._tagController.addTag(data)

    def addTagAtTime(self, data, time):
        self._tagController.addTagAtTime(data, time)

    def addExistingTag(self, data, type):
        return self._tagController.addExistingTag(data, type)

    def editTagTypeOnWave(self, data):
        self._tagController.editTagTypeOnWave(data)

    def playOrPause(self, action):
        self._renderer.playOrPause(action)

    def playAndPause(self):
        self._renderer.playAndPause()
