import os.path

import pyqtgraph as pg
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QPushButton,
                            QFileDialog, QApplication, QHBoxLayout, QSlider,
                            QLabel, QGroupBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPointF
import numpy as np
import librosa
import soundfile as sf
import sys

class WaveWidget(pg.PlotWidget):
    def __init__(self, audioData, sr):
        super().__init__()
        self.audioData = audioData
        self.sr = sr
        self.duration = len(self.audioData)/self.sr
        self.vb = self.getViewBox()

        self.init_ui()
        self.setupZooming()

    def init_ui(self):
        self.setFixedHeight(200)
        self.clear()

        self.setStyleSheet("QGraphicsView { border: 2px solid black; }")
        self.setLabel("left", 'Амплитуда')
        self.setLabel('bottom', 'Time', units='s')
        self.setBackground('w')
        self.showGrid(x=True, y=True, alpha=0.3)
        self.drawWave()

        self.vb.setLimits(
            xMin=0,
            xMax=self.duration,
            yMin=-1,
            yMax=1,
            minXRange=0.001,
            maxXRange=self.duration
        )

        self.setMenuEnabled(False)
        self.vb.disableAutoRange()


    def drawWave(self):
        timeAxis = np.linspace(0, self.duration, len(self.audioData))

        if len(self.audioData) > 100000:
            downsampleFactor = len(self.audioData) // 100000

            x_down = timeAxis[::downsampleFactor]
            y_down = self.audioData[::downsampleFactor]

            self.plot(x_down, y_down, pen=pg.mkPen('b', width=1))
        else:
            self.plot(timeAxis, self.audioData, pen=pg.mkPen('b', width=1))

        #центральная линия
        self.zeroLine = pg.InfiniteLine(pos = 0, angle=0, pen=pg.mkPen('r', width=1))
        self.addItem(self.zeroLine)

        #выделение области
        self.region = pg.LinearRegionItem([self.duration/4, self.duration/2])
        self.region.setZValue(-10)
        self.addItem(self.region)

        #курсор
        self.vLine = pg.InfiniteLine(pos=0, angle=90, pen='y')
        self.addItem(self.vLine)

        #движение мышью
        self.proxy = pg.SignalProxy(
            self.scene().sigMouseMoved,
            rateLimit=60,
            slot=self.mouseMoved
        )

    def mouseMoved(self, evt):
        pos = evt[0]

        if self.sceneBoundingRect().contains(pos):
            mousePosition = self.vb.mapSceneToView(pos)
            self.vLine.setPos(mousePosition.x())

    def setupZooming(self):

        self.vb.wheelEvent = self.wheelEventFixedCenter
        self.vb.sigRangeChanged.connect(self.updateCenterLine)

    def wheelEventFixedCenter(self, ev, axis=None):
        vr = self.vb.viewRect()
        scenePos = ev.scenePos()
        cursorPos = self.vb.mapSceneToView(scenePos)

        center = QPointF(cursorPos.x(), vr.center().y())
        print(vr.center(), ev.screenPos(), ev.screenPos().x())

        s = 1.02 ** (ev.delta() * self.vb.state['wheelScaleFactor'])

        self.vb.scaleBy([s, 1], center)

        ev.accept()

        self.updateVisibleFragment()

    def updateCenterLine(self):
        currentRange = self.vb.viewRange()[0]
        centerX = (currentRange[0] + currentRange[1]) / 2
        self.zeroLine.setPos(centerX)

    def updateVisibleFragment(self):
        currentRange = self.vb.viewRange()[0]
        vissibleDuration = currentRange[1] - currentRange[0]



class ProjectWindow(QMainWindow):
    def __init__(self, project_data):
        super().__init__()
        self.project_data = project_data
        self.audio = None
        self.sr = None

        self.init_ui()


    def init_ui(self):
        self.setWindowTitle(self.project_data['project_name'])
        self.setGeometry(100, 100, 1400, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)

        addButton = QPushButton("Add track")
        addButton.clicked.connect(self.addTrack)
        self.layout.addWidget(addButton)

        waveButton = QPushButton("Add wave")
        waveButton.clicked.connect(self.addWave)
        self.layout.addWidget(waveButton)

    def addTrack(self):
        filePath, _ = QFileDialog.getOpenFileName(
            self,
            "Choose audio",
            "",
            "Аудио файлы (*.mp3, *.wav, *.flac, *.ogg, *.m4a);;Все файлы (*)"
        )
        if not os.path.exists(filePath):
            print("File not exist")
            return
        try:
            self.audio, self.sr = librosa.load(filePath, sr=None, mono=True)
        except Exception as e:
            print(e)
            return

    def addWave(self):
        if self.audio is not None and self.sr is not None:
            wave = WaveWidget(self.audio, self.sr)
            self.layout.addWidget(wave)

