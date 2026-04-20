import logging
import time

import pyqtgraph as pg

from PyQt6.QtCore import QPointF, QUrl, QTimer
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
import numpy as np

import librosa

from ProjectScreen.TagLogic.ruler_format import format_tick_strings
from lightconductor.application.beat_detection import detect_beats

logger = logging.getLogger(__name__)


class WaveRenderer:
    _format_tick_strings = staticmethod(format_tick_strings)

    def __init__(self, plot_widget, audioData, sr, audioPath):
        self._plot_widget = plot_widget
        self.vb = plot_widget.getViewBox()
        self.setAudioData(audioData, sr, audioPath)

    def setAudioData(self, audioData, sr, audioPath):
        self.audioPath = audioPath
        if audioData is None or sr in (None, 0):
            self.audioData = np.array([0.0], dtype=float)
            self.sr = 1
            self.duration = 1.0
            self.durationMs = 0.0
            self.hasAudio = False
            self.beat_times = np.empty(0, dtype=float)
            return

        self.audioData = audioData
        self.sr = sr
        self.duration = len(self.audioData) / self.sr
        self.durationMs = librosa.get_duration(y=self.audioData, sr=self.sr)
        self.hasAudio = True

        start_perf = time.perf_counter()
        try:
            beat_times = detect_beats(self.audioData, self.sr)
        except Exception:
            logger.exception("Beat detection failed unexpectedly; using no beats")
            beat_times = np.empty(0, dtype=float)
        elapsed_ms = (time.perf_counter() - start_perf) * 1000.0
        if elapsed_ms > 500.0:
            logger.warning(
                "Beat detection slow: %d beats in %.1f ms (duration=%.3fs)",
                len(beat_times), elapsed_ms, self.duration,
            )
        else:
            logger.info(
                "Beat detection: %d beats in %.1f ms", len(beat_times), elapsed_ms,
            )
        self.beat_times = beat_times

    def init_ui(self):
        self.initAudioPlayer()

        self._plot_widget.setFixedHeight(200)
        self._plot_widget.clear()

        self._plot_widget.setStyleSheet("QGraphicsView { border: 2px solid black; }")
        self._plot_widget.hideAxis("left")
        bottom_axis = self._plot_widget.getAxis('bottom')
        bottom_axis.tickStrings = WaveRenderer._format_tick_strings
        self._plot_widget.setLabel('bottom', '')
        self._plot_widget.setBackground('w')
        self.drawWave()

        self.vb.setLimits(
            xMin=0,
            xMax=self.duration,
            yMin=-1,
            yMax=1,
            minXRange=0.05,
            maxXRange=self.duration
        )

        self._plot_widget.setMenuEnabled(False)
        self.vb.disableAutoRange()


    def drawWave(self):
        timeAxis = np.linspace(0, self.duration, len(self.audioData))

        if len(self.audioData) > 100000:
            downsampleFactor = len(self.audioData) // 100000

            x_down = timeAxis[::downsampleFactor]
            y_down = self.audioData[::downsampleFactor]

            self._plot_widget.plot(x_down, y_down, pen=pg.mkPen('b', width=1))
        else:
            self._plot_widget.plot(timeAxis, self.audioData, pen=pg.mkPen('b', width=1))

        #центральная линия
        self.zeroLine = pg.InfiniteLine(pos = 0, angle=0, pen=pg.mkPen('r', width=1))
        self._plot_widget.addItem(self.zeroLine)

        #курсор
        self.vLine = pg.InfiniteLine(pos=0, angle=90, pen='y')
        self._plot_widget.addItem(self.vLine)

        #метка
        self.selectedLine = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen('r', width=1))
        self._plot_widget.addItem(self.selectedLine)

        #движение мышью
        self.proxy = pg.SignalProxy(
            self._plot_widget.scene().sigMouseMoved,
            rateLimit=60,
            slot=self.mouseMoved
        )

    def mouseMoved(self, evt):
        pos = evt[0]

        if self._plot_widget.sceneBoundingRect().contains(pos):
            mousePosition = self.vb.mapSceneToView(pos)
            self.vLine.setPos(mousePosition.x())

    def setupMouse(self):

        self.vb.wheelEvent = self.wheelEventFixedCenter
        self._plot_widget.scene().sigMouseClicked.connect(self.onClick)

    def wheelEventFixedCenter(self, ev, axis=None):
        vr = self.vb.viewRect()
        scenePos = ev.scenePos()
        cursorPos = self.vb.mapSceneToView(scenePos)

        center = QPointF(cursorPos.x(), vr.center().y())

        s = 1.02 ** (ev.delta() * self.vb.state['wheelScaleFactor'])

        self.vb.scaleBy([s, 1], center)

        ev.accept()


    def updateVisibleFragment(self):
        currentRange = self.vb.viewRange()[0]
        vissibleDuration = currentRange[1] - currentRange[0]


    def onClick(self, ev):
        pos = ev.scenePos()

        if self._plot_widget.sceneBoundingRect().contains(pos):
            mousePosition = self.vb.mapSceneToView(pos)
            self.audioPlayer.setPosition(round(round(mousePosition.x(), 1) * 1000))

    def initAudioPlayer(self):
        self.audioPlayer = QMediaPlayer()
        if self.audioPath:
            self.audioPlayer.setSource(QUrl.fromLocalFile(self.audioPath))
        self.audioOutput = QAudioOutput()
        self.audioPlayer.setAudioOutput(self.audioOutput)
        self.audioPlayer.positionChanged.connect(self.onPositionChanged)

    def onPositionChanged(self, positionMs):
        positioRatio = positionMs / 1000
        self.selectedLine.setValue(positioRatio)

        minutes = positionMs // 60000
        seconds = (positionMs % 60000) // 1000
        ms = (positionMs % 60000) % 1000
        timeStr = f"{minutes}:{seconds}:{ms}"
        self._plot_widget.positionUpdate.emit(positioRatio, timeStr)

    def playOrPause(self, action):
        if action == "Play":
            self.audioPlayer.play()
        else:
            self.audioPlayer.pause()
    def playAndPause(self):
        self.audioPlayer.play()
        QTimer.singleShot(100, self.audioPlayer.pause)
