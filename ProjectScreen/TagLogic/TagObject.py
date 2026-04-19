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

    def deleteTag(self):
        type_ = self.type
        manager = self.manager
        type_name = type_.name if type_ is not None else None
        # Find scene tag index via the controller registry, which is
        # kept in lockstep sort order with state.
        wave = (
            manager.box.wave
            if manager is not None and getattr(manager, "box", None) is not None
            else None
        )
        controller = getattr(wave, "_tagController", None)
        idx = None
        if controller is not None and type_name is not None:
            try:
                idx = controller.scene_tags_for(type_name).index(self)
            except ValueError:
                idx = None
        state = getattr(manager, "_state", None)
        project_window = getattr(manager, "_project_window", None)
        if (
            state is not None
            and project_window is not None
            and not project_window.is_loading()
            and idx is not None
            and type_ is not None
            and type_.master_id is not None
            and type_.slave_id is not None
        ):
            try:
                state.remove_tag(
                    type_.master_id,
                    type_.slave_id,
                    type_name,
                    idx,
                )
            except (KeyError, IndexError):
                import logging
                logging.getLogger(__name__).warning(
                    "state missing tag during delete: type=%s idx=%s",
                    type_name, idx,
                )
        if controller is not None and type_name is not None:
            controller.remove_scene_tag(type_name, self)
        else:
            scene = self.scene()
            if scene is not None:
                scene.removeItem(self)
