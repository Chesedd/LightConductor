import numpy as np
import pyqtgraph as pg


class WaveMiniMap(pg.PlotWidget):
    """Compact overview plot with a draggable viewport indicator.

    Shows the entire waveform downsampled to a fixed-height strip, with a
    ``LinearRegionItem`` mirroring the target wave's current X-range.
    Sync is bi-directional via ``sigRangeChanged`` / ``sigRegionChanged``
    and guarded by ``self._syncing`` to prevent recursive callbacks.
    """

    def __init__(self, target_wave, audioData, sr, duration, parent=None):
        super().__init__(parent)
        self._target_wave = target_wave
        self._syncing = False
        self._wave_curve = None
        self._signals_wired = False

        self.setFixedHeight(55)
        self.setStyleSheet("QGraphicsView { border: 1px solid #888; }")
        self.setMenuEnabled(False)
        self.hideAxis("left")
        self.hideAxis("bottom")
        self.setBackground("w")

        self.vb = self.getViewBox()
        self.vb.setMouseEnabled(x=False, y=False)
        self.vb.disableAutoRange()

        initial_dur = max(float(duration or 0.0), 0.001)
        self.region = pg.LinearRegionItem(
            values=(0.0, initial_dur),
            orientation="vertical",
            brush=pg.mkBrush(100, 100, 255, 50),
            pen=pg.mkPen("b", width=1),
            movable=True,
        )
        self.region.setZValue(10)
        self.addItem(self.region)

    def setData(self, audioData, sr, duration):
        if self._wave_curve is not None:
            self.removeItem(self._wave_curve)
            self._wave_curve = None

        empty = (
            audioData is None
            or len(audioData) == 0
            or sr in (None, 0)
            or duration is None
            or float(duration) <= 0.0
        )

        if empty:
            dur = max(float(duration or 0.0), 1.0)
            self.vb.setLimits(
                xMin=0,
                xMax=dur,
                yMin=-1,
                yMax=1,
                minXRange=dur,
                maxXRange=dur,
            )
            self.vb.setRange(xRange=(0, dur), yRange=(-1, 1), padding=0)
            self._set_region_safely((0.0, dur))
            self.region.setBounds((0.0, dur))
        else:
            dur = float(duration)
            timeAxis = np.linspace(0, dur, len(audioData))
            if len(audioData) > 10000:
                factor = len(audioData) // 10000
                x = timeAxis[::factor]
                y = audioData[::factor]
            else:
                x, y = timeAxis, audioData
            self._wave_curve = self.plot(x, y, pen=pg.mkPen("b", width=1))

            self.vb.setLimits(
                xMin=0,
                xMax=dur,
                yMin=-1,
                yMax=1,
                minXRange=dur,
                maxXRange=dur,
            )
            self.vb.setRange(xRange=(0, dur), yRange=(-1, 1), padding=0)

            try:
                (x0, x1), _ = self._target_wave.vb.viewRange()
            except Exception:
                x0, x1 = 0.0, dur
            self._set_region_safely((float(x0), float(x1)))
            self.region.setBounds((0.0, dur))

        if not self._signals_wired:
            self.region.sigRegionChanged.connect(self._on_region_changed)
            self._target_wave.vb.sigRangeChanged.connect(self._on_target_range_changed)
            self._signals_wired = True

    def _set_region_safely(self, rgn):
        self._syncing = True
        try:
            self.region.setRegion(rgn)
        finally:
            self._syncing = False

    def _on_region_changed(self):
        if self._syncing:
            return
        x0, x1 = self.region.getRegion()
        if x1 <= x0:
            return
        self._syncing = True
        try:
            self._target_wave.vb.setXRange(float(x0), float(x1), padding=0)
        finally:
            self._syncing = False

    def _on_target_range_changed(self, vb, ranges):
        if self._syncing:
            return
        try:
            x0, x1 = ranges[0]
        except Exception:
            return
        self._syncing = True
        try:
            self.region.setRegion((float(x0), float(x1)))
        finally:
            self._syncing = False
