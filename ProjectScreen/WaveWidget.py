import pyqtgraph as pg

from PyQt6.QtGui import QColor
from PyQt6.QtCore import QPointF
import numpy as np

from ProjectScreen.TagObject import Tag
from ProjectScreen.TagManager import TagManager

class WaveWidget(pg.PlotWidget):
    def __init__(self, audioData, sr, manager):
        super().__init__()
        self.manager = manager
        self.audioData = audioData
        self.sr = sr
        self.duration = len(self.audioData)/self.sr
        self.vb = self.getViewBox()

        self.init_ui()
        self.setupMouse()

    def init_ui(self):
        self.setFixedHeight(200)
        self.clear()

        self.setStyleSheet("QGraphicsView { border: 2px solid black; }")
        self.hideAxis("left")
        self.setLabel('bottom', 'Time', units='s')
        self.setBackground('w')
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

        #курсор
        self.vLine = pg.InfiniteLine(pos=0, angle=90, pen='y')
        self.addItem(self.vLine)

        #метка
        self.selectedLine = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen('r', width=1))
        self.addItem(self.selectedLine)

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

    def setupMouse(self):

        self.vb.wheelEvent = self.wheelEventFixedCenter
        self.scene().sigMouseClicked.connect(self.onClick)

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

        if self.sceneBoundingRect().contains(pos):
            mousePosition = self.vb.mapSceneToView(pos)
            self.selectedLine.setPos(mousePosition.x())

    def addTag(self):
        color = self.manager.curType.color
        r, g, b = map(int, color.split(','))
        tag = Tag(pos = self.selectedLine.pos(), angle=90, pen=pg.mkPen(QColor(r, g, b), width=1))
        self.addItem(tag)
        self.manager.curType.addTag(tag)
