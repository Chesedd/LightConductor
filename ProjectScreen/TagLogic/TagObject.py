from pyqtgraph import  InfiniteLine
from PyQt6 import QtWidgets, QtCore

from lightconductor.application.commands import DeleteTagCommand

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
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt as QtEnum
        # Find the controller via manager.box.wave._tagController.
        # Same resolution pattern used by deleteTag below.
        controller = None
        manager = getattr(self, "manager", None)
        if manager is not None:
            box = getattr(manager, "box", None)
            if box is not None:
                wave = getattr(box, "wave", None)
                if wave is not None:
                    controller = getattr(wave, "_tagController", None)
        mods = QApplication.keyboardModifiers()
        is_extend = bool(
            mods & (
                QtEnum.KeyboardModifier.ControlModifier
                | QtEnum.KeyboardModifier.ShiftModifier
            )
        )
        if controller is not None:
            if is_extend:
                controller.toggle_selection(self)
            else:
                controller.select_only(self)
        # Snapshot origin times if a group-drag is about to start.
        if controller is not None and self.movable:
            controller.notify_drag_started(self)
        # Preserve the existing single-tag info-panel behavior
        # for plain clicks. On extend-clicks, still set the
        # TagInfoScreen to this tag — user's last-clicked tag
        # is the panel subject.
        if self.manager is not None and self.manager.tagScreen is not None:
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
        wave = (
            manager.box.wave
            if manager is not None and getattr(manager, "box", None) is not None
            else None
        )
        controller = getattr(wave, "_tagController", None)
        state = getattr(manager, "_state", None)
        project_window = getattr(manager, "_project_window", None)
        commands = getattr(manager, "_commands", None)
        # State-first delete: resolve the tag's index via the scene
        # registry (kept in lockstep with state) and ask state to
        # remove. The TagRemoved listener on the controller then
        # detaches the scene item. If no state is wired (headless /
        # legacy instantiation), fall back to direct scene removal.
        if (
            state is not None
            and project_window is not None
            and not project_window.is_loading()
            and controller is not None
            and type_ is not None
            and type_name is not None
            and type_.master_id is not None
            and type_.slave_id is not None
        ):
            try:
                idx = controller.scene_tags_for(type_name).index(self)
            except ValueError:
                idx = None
            if idx is not None:
                try:
                    if commands is not None:
                        commands.push(
                            DeleteTagCommand(
                                master_id=type_.master_id,
                                slave_id=type_.slave_id,
                                type_name=type_name,
                                tag_index=idx,
                            )
                        )
                    else:
                        state.remove_tag(
                            type_.master_id,
                            type_.slave_id,
                            type_name,
                            idx,
                        )
                    return
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
