from pyqtgraph import  InfiniteLine
from PyQt6 import QtWidgets, QtCore

class Tag(InfiniteLine):
    def __init__(self, action=None, colors=None, pos=None, angle=90, pen=None, movable=False, bounds=None,
                 hoverPen=None, type=None, manager = None):

        super().__init__(pos=pos, angle=angle, pen=pen, movable=movable,
                         bounds=bounds, hoverPen=hoverPen, name=None)
        self.time = pos.x()
        self.action = action
        self.colors = colors
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
        self.action = params["action"]
        self.colors = params["colors"]
        self.setPos(self.time)
        self.type.editTag()

    def deleteTag(self):
        self.type.deleteTag(self)
        self.scene().removeItem(self)
