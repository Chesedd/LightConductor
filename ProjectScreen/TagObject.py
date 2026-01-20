from pyqtgraph import  InfiniteLine
from PyQt6 import QtWidgets, QtCore

class Tag(InfiniteLine):
    def __init__(self, state=None, pos=None, angle=90, pen=None, movable=False, bounds=None,
                 hoverPen=None, type=None, manager = None):

        super().__init__(pos=pos, angle=angle, pen=pen, movable=movable,
                         bounds=bounds, hoverPen=hoverPen, name=None)
        self.time = pos.x()
        self.state = state
        self.type = type
        self.manager = manager
        self.setAcceptHoverEvents(True)
        self.setZValue(100)


    def mousePressEvent(self, event):
        self.manager.tagScreen.setTag(self)
        super().mousePressEvent(event)
    def hoverEnterEvent(self, event):
        if self.movable:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.SizeHorCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        QtWidgets.QApplication.restoreOverrideCursor()
        super().hoverLeaveEvent(event)

    def editParams(self, params):
        self.time = float(params["time"])
        if params["state"] == "True":
            self.state = True
        else:
            self.state = False
        self.setPos(self.time)
        self.type.editTag()
