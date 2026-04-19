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
        # Compute tag_index from widget-side TagType.tags before
        # the widget-side removal shifts it.
        tag_index = None
        type_ = self.type
        if type_ is not None:
            try:
                tag_index = type_.tags.index(self)
            except ValueError:
                tag_index = None
        state = getattr(self.manager, "_state", None)
        project_window = getattr(self.manager, "_project_window", None)
        if (
            state is not None
            and project_window is not None
            and not project_window.is_loading()
            and tag_index is not None
            and type_ is not None
            and type_.master_id is not None
            and type_.slave_id is not None
        ):
            try:
                state.remove_tag(
                    type_.master_id,
                    type_.slave_id,
                    type_.name,
                    tag_index,
                )
            except (KeyError, IndexError):
                import logging
                logging.getLogger(__name__).warning(
                    "state missing tag during delete: type=%s index=%s",
                    type_.name, tag_index,
                )
        self.type.deleteTag(self)
        self.scene().removeItem(self)
