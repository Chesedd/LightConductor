from typing import Optional

from PyQt6 import QtCore, QtWidgets
from pyqtgraph import InfiniteLine

from lightconductor.application.commands import DeleteTagCommand

# A press is treated as a click (open the edit dialog on release)
# only when the cursor barely moved AND the press-to-release
# duration is short. Anything beyond either threshold is read as
# a drag and leaves the dialog closed. Module-level constants so
# tests can monkeypatch them in isolation.
CLICK_PIXEL_THRESHOLD = 4.0
CLICK_TIME_THRESHOLD_S = 0.30


def _is_click_release(
    *,
    press_pos_x: Optional[float],
    press_pos_y: Optional[float],
    release_pos_x: float,
    release_pos_y: float,
    press_monotonic: Optional[float],
    release_monotonic: float,
    was_extend: bool,
    pixel_threshold: float = CLICK_PIXEL_THRESHOLD,
    time_threshold_s: float = CLICK_TIME_THRESHOLD_S,
) -> bool:
    """Decide whether a release should open the edit dialog.

    Modifier-press is a pure selection gesture and never opens
    the dialog. A missing press snapshot (no matching press) is
    also a no-op. Otherwise the release is a click iff the
    cursor moved <= pixel_threshold AND the elapsed time is
    <= time_threshold_s.
    """
    if was_extend:
        return False
    if press_pos_x is None or press_pos_y is None or press_monotonic is None:
        return False
    dx = release_pos_x - press_pos_x
    dy = release_pos_y - press_pos_y
    moved = (dx * dx + dy * dy) ** 0.5
    elapsed = release_monotonic - press_monotonic
    return moved <= pixel_threshold and elapsed <= time_threshold_s


class Tag(InfiniteLine):
    def __init__(
        self,
        action=None,
        colors=None,
        pos=None,
        angle=90,
        pen=None,
        movable=False,
        bounds=None,
        hoverPen=None,
        type=None,
        manager=None,
    ):

        super().__init__(
            pos=pos,
            angle=angle,
            pen=pen,
            movable=movable,
            bounds=bounds,
            hoverPen=hoverPen,
            name=None,
        )
        self.time = pos.x()
        self.action = action
        self.colors = colors
        self.type = type
        self.manager = manager
        self.setAcceptHoverEvents(True)
        self.setZValue(100)
        # Press snapshot consumed by mouseReleaseEvent to decide
        # click-vs-drag. Initialized so a release without a
        # matching press is a safe no-op.
        self._press_scene_pos = None
        self._press_monotonic = None
        self._press_was_extend = False

    def mousePressEvent(self, event):
        import time as _time

        from PyQt6.QtCore import Qt as QtEnum
        from PyQt6.QtWidgets import QApplication

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
            mods
            & (
                QtEnum.KeyboardModifier.ControlModifier
                | QtEnum.KeyboardModifier.ShiftModifier
            )
        )
        # Selection update — preserve the existing multi-selection
        # when a member is pressed without modifiers, so the
        # subsequent group-drag has all origins to mirror against.
        in_group = (
            controller is not None
            and self in getattr(controller, "_selected_tags", set())
            and len(getattr(controller, "_selected_tags", set())) > 1
        )
        if controller is not None:
            if is_extend:
                controller.toggle_selection(self)
            elif in_group:
                # Preserve the existing selection. Anchor stays
                # this tag so notify_drag_started snapshots the
                # whole group around it.
                pass
            else:
                controller.select_only(self)
        # Snapshot origin times if a group-drag is about to start.
        # No-ops safely when self is not in selection or selection
        # is a singleton.
        if controller is not None and self.movable:
            controller.notify_drag_started(self)
        # Defer the dialog-open decision to mouseReleaseEvent —
        # opening here would steal focus from any in-progress drag
        # and break the group-drag pipeline.
        try:
            self._press_scene_pos = event.scenePos()
        except Exception:
            self._press_scene_pos = None
        self._press_monotonic = _time.monotonic()
        self._press_was_extend = is_extend
        # Accept the event so Qt does not propagate it to other
        # TagObjects whose bounding rects overlap this click point.
        # At 0.02s grid spacing, neighbor tag bounding rects commonly
        # overlap any single click; without accept(), each tag under
        # the cursor would open its own edit window. The pyqtgraph
        # InfiniteLine base does not define mousePressEvent, so the
        # super chain ends at QGraphicsObject whose default
        # implementation calls event.ignore() for non-movable /
        # non-selectable items — exactly the propagation we need to
        # suppress. Drag handling flows through mouseDragEvent
        # (separate signal path), not through this handler, so
        # skipping super here costs us no built-in behavior.
        event.accept()

    def mouseReleaseEvent(self, event):
        import time as _time

        press_pos = getattr(self, "_press_scene_pos", None)
        press_t = getattr(self, "_press_monotonic", None)
        was_extend = getattr(self, "_press_was_extend", False)
        # Clear stash regardless of decision so a stray release
        # without a matching press cannot replay stale state.
        self._press_scene_pos = None
        self._press_monotonic = None
        self._press_was_extend = False
        try:
            release_pos = event.scenePos()
        except Exception:
            event.accept()
            return
        press_pos_x = press_pos.x() if press_pos is not None else None
        press_pos_y = press_pos.y() if press_pos is not None else None
        if _is_click_release(
            press_pos_x=press_pos_x,
            press_pos_y=press_pos_y,
            release_pos_x=release_pos.x(),
            release_pos_y=release_pos.y(),
            press_monotonic=press_t,
            release_monotonic=_time.monotonic(),
            was_extend=was_extend,
        ):
            manager = getattr(self, "manager", None)
            if manager is not None:
                project_window = getattr(manager, "_project_window", None)
                if project_window is not None and hasattr(
                    project_window, "openTagEditWindow"
                ):
                    project_window.openTagEditWindow(self)
        event.accept()

    def hoverEnterEvent(self, event):
        if self.movable:
            try:
                QtWidgets.QApplication.setOverrideCursor(
                    QtCore.Qt.CursorShape.SizeHorCursor
                )
            except Exception:
                pass
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        try:
            QtWidgets.QApplication.restoreOverrideCursor()
        except Exception:
            pass
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
                        type_name,
                        idx,
                    )
        if controller is not None and type_name is not None:
            controller.remove_scene_tag(type_name, self)
        else:
            scene = self.scene()
            if scene is not None:
                scene.removeItem(self)
