import bisect
import logging
from typing import Dict, List, Optional, Set, Tuple

import pyqtgraph as pg
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from lightconductor.application.beat_detection import snap_to_nearest_beat
from lightconductor.application.commands import AddTagCommand, MoveTagCommand
from lightconductor.application.project_state import (
    TagAdded,
    TagRemoved,
    TagUpdated,
)
from lightconductor.domain.models import Tag as DomainTag
from ProjectScreen.TagLogic.TagObject import Tag

SNAP_GRANULARITY_SECONDS = 0.02


logger = logging.getLogger(__name__)


class TagTimelineController:
    def __init__(
        self,
        plot_widget,
        manager,
        renderer,
        state=None,
        project_window=None,
        master_id=None,
        slave_id=None,
        commands=None,
    ):
        self._plot_widget = plot_widget
        self._manager = manager
        self._renderer = renderer
        self._state = state
        self._project_window = project_window
        self._master_id = master_id
        self._slave_id = slave_id
        self._commands = commands
        self._scene_tags: Dict[str, List[Tag]] = {}
        # Identity map from domain Tag object (by id()) to the scene
        # Tag that represents it. Populated by _handle_tag_added and
        # consulted by _handle_tag_updated to locate the scene tag
        # regardless of its current position in the time-sorted list.
        self._scene_by_domain_id: Dict[int, Tag] = {}
        self._selected_tags: Set[Tag] = set()
        self._drag_anchor_tag: Optional[Tag] = None
        self._drag_group_origin: Dict[int, float] = {}
        self._orig_vb_mouse_press = None
        self._orig_vb_mouse_move = None
        self._orig_vb_mouse_release = None
        self._rubber_band_item = None
        self._rubber_band_start_x: Optional[float] = None
        self._rubber_band_active: bool = False
        self._unsubscribe = None
        if self._state is not None:
            self._unsubscribe = self._state.subscribe(self._on_state_event)

    def _insert_sorted_scene_tag(self, type_name, tag):
        lst = self._scene_tags.setdefault(type_name, [])
        idx = bisect.bisect_left([t.time for t in lst], tag.time)
        lst.insert(idx, tag)
        return idx

    def resort_scene_tags(self, type_name):
        lst = self._scene_tags.get(type_name)
        if lst:
            lst.sort(key=lambda t: t.time)

    def scene_tags_for(self, type_name):
        return list(self._scene_tags.get(type_name, []))

    def remove_scene_tag_type(self, type_name):
        for tag in self._scene_tags.get(type_name, []):
            scene = tag.scene()
            if scene is not None:
                scene.removeItem(tag)
            self._scene_by_domain_id = {
                did: st for did, st in self._scene_by_domain_id.items() if st is not tag
            }
        self._selected_tags -= set(self._scene_tags.get(type_name, []))
        self._scene_tags.pop(type_name, None)

    def remove_scene_tag(self, type_name, tag_item):
        lst = self._scene_tags.get(type_name)
        if lst is not None:
            try:
                lst.remove(tag_item)
            except ValueError:
                pass
        self._selected_tags.discard(tag_item)
        scene = tag_item.scene()
        if scene is not None:
            scene.removeItem(tag_item)
        for did, st in list(self._scene_by_domain_id.items()):
            if st is tag_item:
                del self._scene_by_domain_id[did]
                break

    def selected_scene_tags(self) -> List[Tag]:
        """Return selected scene tags as a list (stable,
        deterministic ordering by (type_name, scene-index))."""
        result: List[Tuple[str, int, Tag]] = []
        for type_name, lst in self._scene_tags.items():
            for idx, t in enumerate(lst):
                if t in self._selected_tags:
                    result.append((type_name, idx, t))
        result.sort(key=lambda e: (e[0], e[1]))
        return [t for _, _, t in result]

    def is_selected(self, scene_tag: Tag) -> bool:
        return scene_tag in self._selected_tags

    def clear_selection(self) -> None:
        for t in list(self._selected_tags):
            self._apply_selection_visual(t, selected=False)
        self._selected_tags.clear()

    def select_only(self, scene_tag: Tag) -> None:
        """Replace selection with a single tag (plain-click
        semantics)."""
        self.clear_selection()
        self._selected_tags.add(scene_tag)
        self._apply_selection_visual(scene_tag, selected=True)

    def toggle_selection(self, scene_tag: Tag) -> None:
        """Toggle membership (Ctrl/Shift-click semantics)."""
        if scene_tag in self._selected_tags:
            self._selected_tags.discard(scene_tag)
            self._apply_selection_visual(scene_tag, selected=False)
        else:
            self._selected_tags.add(scene_tag)
            self._apply_selection_visual(scene_tag, selected=True)

    def _apply_selection_visual(
        self,
        scene_tag: Tag,
        selected: bool,
    ) -> None:
        type_ = getattr(scene_tag, "type", None)
        if type_ is None:
            return
        r, g, b = self._parse_color(type_.color)
        width = 5 if selected else 3
        scene_tag.setPen(
            pg.mkPen(QColor(r, g, b), width=width),
        )

    def _on_state_event(self, event):
        # Filter events that don't target this (master, slave). Events
        # that don't carry master_id / slave_id (StateReplaced,
        # MasterAdded, ...) are ignored here; they'll be handled by
        # higher-level bridges in later phases.
        if getattr(event, "master_id", None) != self._master_id:
            return
        if getattr(event, "slave_id", None) != self._slave_id:
            return
        if isinstance(event, TagAdded):
            self._handle_tag_added(event)
        elif isinstance(event, TagRemoved):
            self._handle_tag_removed(event)
        elif isinstance(event, TagUpdated):
            self._handle_tag_updated(event)

    def _domain_tag_list(self, type_name):
        if self._state is None:
            return None
        try:
            return (
                self._state.master(self._master_id)
                .slaves[self._slave_id]
                .tag_types[type_name]
                .tags
            )
        except KeyError:
            return None

    def _parse_color(self, color):
        if isinstance(color, str):
            return tuple(int(c) for c in color.split(","))
        return int(color[0]), int(color[1]), int(color[2])

    def _drag_bounds(self):
        dur = float(getattr(self._renderer, "duration", 0.0) or 0.0)
        if dur <= 0.0:
            return None
        return (0.0, dur)

    def _create_scene_tag(self, time_value, action, colors, widget_type):
        r, g, b = self._parse_color(widget_type.color)
        tag = Tag(
            pos=QPointF(float(time_value), 0.0),
            angle=90,
            pen=pg.mkPen(QColor(r, g, b), width=3),
            movable=True,
            bounds=self._drag_bounds(),
            action=action,
            colors=colors,
            type=widget_type,
            manager=self._manager,
        )
        self._wire_drag_signals(tag)
        return tag

    def _wire_drag_signals(self, scene_tag):
        scene_tag.sigPositionChanged.connect(
            lambda _line, t=scene_tag: self._on_tag_position_changed(t)
        )
        scene_tag.sigPositionChangeFinished.connect(
            lambda _line, t=scene_tag: self._on_tag_drag_finished(t)
        )

    def _on_tag_position_changed(self, scene_tag):
        tag_info = getattr(self._manager, "tagScreen", None)
        if tag_info is not None and getattr(tag_info, "tag", None) is scene_tag:
            try:
                new_x = float(scene_tag.value())
            except (TypeError, ValueError):
                return
            scene_tag.time = new_x
            if getattr(tag_info, "tagTimeText", None) is not None:
                tag_info.tagTimeText.setText(f"{new_x:.3f}")
        # If this scene_tag is the anchor of an active bulk
        # drag, mirror its delta across the selection.
        if (
            scene_tag is self._drag_anchor_tag
            and scene_tag in self._selected_tags
            and len(self._selected_tags) > 1
        ):
            try:
                anchor_new = float(scene_tag.value())
            except (TypeError, ValueError):
                return
            anchor_origin = self._drag_group_origin.get(id(scene_tag))
            if anchor_origin is None:
                return
            delta = anchor_new - anchor_origin
            from PyQt6.QtCore import QSignalBlocker

            for other in self._selected_tags:
                if other is scene_tag:
                    continue
                other_origin = self._drag_group_origin.get(id(other))
                if other_origin is None:
                    continue
                blocker = QSignalBlocker(other)
                try:
                    other.setPos(other_origin + delta)
                    other.time = other_origin + delta
                finally:
                    del blocker

    def _find_domain_id_for_scene_tag(self, scene_tag):
        for did, st in self._scene_by_domain_id.items():
            if st is scene_tag:
                return did
        return None

    def notify_drag_started(self, scene_tag):
        """Called from Tag.mousePressEvent when a move is
        initiated. Captures the pre-drag time of every selected
        scene tag (so we can compute deltas later) if the pressed
        tag is part of the selection."""
        if scene_tag not in self._selected_tags:
            self._drag_anchor_tag = None
            self._drag_group_origin = {}
            return
        self._drag_anchor_tag = scene_tag
        self._drag_group_origin = {id(t): float(t.value()) for t in self._selected_tags}

    def _on_tag_drag_finished(self, scene_tag):
        # Group drag: anchor matches and selection > 1.
        if (
            scene_tag is self._drag_anchor_tag
            and scene_tag in self._selected_tags
            and len(self._selected_tags) > 1
        ):
            self._finish_bulk_drag(scene_tag)
            return
        # Single-tag path (existing 4.3b behavior verbatim).
        self._finish_single_drag(scene_tag)

    def _finish_single_drag(self, scene_tag):
        shift_held = bool(
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        )
        beats = getattr(self._renderer, "beat_times", None) if shift_held else None
        raw_time = max(0.0, float(scene_tag.value()))
        snapped = snap_to_nearest_beat(
            raw_time,
            beats,
            SNAP_GRANULARITY_SECONDS,
        )
        dur = float(getattr(self._renderer, "duration", 0.0) or 0.0)
        if dur > 0.0 and snapped > dur:
            snapped = dur
        type_ = getattr(scene_tag, "type", None)
        type_name = type_.name if type_ is not None else None
        if type_name is None:
            return
        domain_id = self._find_domain_id_for_scene_tag(scene_tag)
        if self._state is None or self._master_id is None or self._slave_id is None:
            scene_tag.setPos(snapped)
            scene_tag.time = snapped
            return
        if domain_id is None:
            logger.warning(
                "drag-finish: scene tag missing from domain registry (type=%s)",
                type_name,
            )
            return
        tags = self._domain_tag_list(type_name)
        if tags is None:
            return
        idx = None
        for i, dt in enumerate(tags):
            if id(dt) == domain_id:
                idx = i
                break
        if idx is None:
            return
        old_time = float(tags[idx].time_seconds)
        if abs(old_time - snapped) < 1e-6:
            scene_tag.setPos(old_time)
            scene_tag.time = old_time
            return
        if self._commands is not None:
            try:
                self._commands.push(
                    MoveTagCommand(
                        master_id=self._master_id,
                        slave_id=self._slave_id,
                        type_name=type_name,
                        tag_index=idx,
                        new_time_seconds=snapped,
                    )
                )
            except (KeyError, IndexError):
                logger.warning(
                    "MoveTagCommand push failed: type=%s idx=%s",
                    type_name,
                    idx,
                )
                scene_tag.setPos(old_time)
                scene_tag.time = old_time
        else:
            try:
                self._state.update_tag(
                    self._master_id,
                    self._slave_id,
                    type_name,
                    idx,
                    time_seconds=snapped,
                )
            except (KeyError, IndexError):
                scene_tag.setPos(old_time)
                scene_tag.time = old_time

    def _finish_bulk_drag(self, anchor):
        from lightconductor.application.commands import CompositeCommand

        shift_held = bool(
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        )
        beats = getattr(self._renderer, "beat_times", None) if shift_held else None
        dur = float(getattr(self._renderer, "duration", 0.0) or 0.0)
        if self._state is None or self._master_id is None or self._slave_id is None:
            # Headless fallback: no command stack available.
            self._drag_anchor_tag = None
            self._drag_group_origin = {}
            return
        children = []
        for scene_tag in self._selected_tags:
            type_ = getattr(scene_tag, "type", None)
            type_name = type_.name if type_ is not None else None
            if type_name is None:
                continue
            domain_id = self._find_domain_id_for_scene_tag(scene_tag)
            if domain_id is None:
                continue
            tags = self._domain_tag_list(type_name)
            if tags is None:
                continue
            idx_hint = None
            for i, dt in enumerate(tags):
                if id(dt) == domain_id:
                    idx_hint = i
                    break
            if idx_hint is None:
                continue
            raw = max(0.0, float(scene_tag.value()))
            snapped = snap_to_nearest_beat(
                raw,
                beats,
                SNAP_GRANULARITY_SECONDS,
            )
            if dur > 0.0 and snapped > dur:
                snapped = dur
            old_time = float(tags[idx_hint].time_seconds)
            if abs(old_time - snapped) < 1e-6:
                continue
            children.append(
                MoveTagCommand(
                    master_id=self._master_id,
                    slave_id=self._slave_id,
                    type_name=type_name,
                    tag_index=idx_hint,
                    new_time_seconds=snapped,
                    tag_identity=domain_id,
                )
            )
        self._drag_anchor_tag = None
        self._drag_group_origin = {}
        if not children:
            # No-op drag: revert live-echo side effects.
            for scene_tag in list(self._selected_tags):
                type_ = getattr(scene_tag, "type", None)
                type_name = type_.name if type_ is not None else None
                if type_name is None:
                    continue
                tags = self._domain_tag_list(type_name)
                if tags is None:
                    continue
                domain_id = self._find_domain_id_for_scene_tag(scene_tag)
                if domain_id is None:
                    continue
                for dt in tags:
                    if id(dt) == domain_id:
                        scene_tag.setPos(float(dt.time_seconds))
                        scene_tag.time = float(dt.time_seconds)
                        break
            return
        if self._commands is not None:
            try:
                self._commands.push(
                    CompositeCommand(children=children),
                )
            except Exception:
                logger.exception(
                    "bulk-move CompositeCommand push failed",
                )

    def _handle_tag_added(self, event):
        domain_tags = self._domain_tag_list(event.type_name)
        if domain_tags is None or event.tag_index >= len(domain_tags):
            logger.warning(
                "TagAdded refers to missing domain tag: type=%s idx=%s",
                event.type_name,
                event.tag_index,
            )
            return
        domain_tag = domain_tags[event.tag_index]
        widget_type = self._manager.types.get(event.type_name)
        if widget_type is None:
            logger.warning(
                "TagAdded for unknown widget type: %s",
                event.type_name,
            )
            return
        scene_tag = self._create_scene_tag(
            time_value=float(domain_tag.time_seconds),
            action=domain_tag.action,
            colors=list(domain_tag.colors) if domain_tag.colors else domain_tag.colors,
            widget_type=widget_type,
        )
        self._plot_widget.addItem(scene_tag)
        self._insert_sorted_scene_tag(event.type_name, scene_tag)
        self._scene_by_domain_id[id(domain_tag)] = scene_tag

    def _handle_tag_removed(self, event):
        lst = self._scene_tags.get(event.type_name, [])
        if event.tag_index < 0 or event.tag_index >= len(lst):
            logger.warning(
                "TagRemoved index out of range: type=%s idx=%s len=%s",
                event.type_name,
                event.tag_index,
                len(lst),
            )
            return
        scene_tag = lst[event.tag_index]
        scene = scene_tag.scene()
        if scene is not None:
            scene.removeItem(scene_tag)
        del lst[event.tag_index]
        self._selected_tags.discard(scene_tag)
        for did, st in list(self._scene_by_domain_id.items()):
            if st is scene_tag:
                del self._scene_by_domain_id[did]
                break

    def _handle_tag_updated(self, event):
        domain_tags = self._domain_tag_list(event.type_name)
        if domain_tags is None or event.tag_index >= len(domain_tags):
            logger.warning(
                "TagUpdated refers to missing domain tag: type=%s idx=%s",
                event.type_name,
                event.tag_index,
            )
            return
        domain_tag = domain_tags[event.tag_index]
        scene_tag = self._scene_by_domain_id.get(id(domain_tag))
        if scene_tag is None:
            logger.warning(
                "TagUpdated for unknown scene tag: type=%s idx=%s",
                event.type_name,
                event.tag_index,
            )
            return
        scene_tag.time = float(domain_tag.time_seconds)
        scene_tag.action = domain_tag.action
        scene_tag.colors = domain_tag.colors
        scene_tag.setPos(float(domain_tag.time_seconds))
        # Identity is preserved across state-level reposition, but
        # the order in the scene registry may need refreshing.
        self.resort_scene_tags(event.type_name)
        # Refresh TagInfoScreen labels when the selected tag is the
        # one we just updated (drag, undo/redo, programmatic edits).
        # The colors grid is rebuilt only via TagInfoScreen.setTag so
        # we intentionally leave it alone here.
        tag_info = getattr(self._manager, "tagScreen", None)
        if tag_info is not None and getattr(tag_info, "tag", None) is scene_tag:
            time_text = getattr(tag_info, "tagTimeText", None)
            if time_text is not None:
                time_text.setText(str(scene_tag.time))
            action_text = getattr(tag_info, "tagActionText", None)
            if action_text is not None:
                action_text.setText("On" if scene_tag.action else "Off")

    def addTag(self, data):
        self.addTagAtTime(data, self._renderer.selectedLine.pos().x())

    def addTagAtTime(self, data, time):
        curType = self._manager.curType
        if curType is None:
            return
        if self._project_window is not None and self._project_window.is_loading():
            # Load-path mutates state via load_masters only; user-action
            # creation during loading would break the load invariant.
            return
        if self._state is not None:
            domain_tag = DomainTag(
                time_seconds=float(time),
                action=data["action"],
                colors=list(data["colors"]),
            )
            if self._commands is not None:
                self._commands.push(
                    AddTagCommand(
                        master_id=self._master_id,
                        slave_id=self._slave_id,
                        type_name=curType.name,
                        tag=domain_tag,
                    )
                )
            else:
                self._state.add_tag(
                    self._master_id,
                    self._slave_id,
                    curType.name,
                    domain_tag,
                )
            return
        # Headless / no-state path: build scene tag directly so callers
        # that instantiate the controller without ProjectState (tests,
        # legacy entrypoints) keep working.
        tag = self._create_scene_tag(
            time_value=time,
            action=data["action"],
            colors=data["colors"],
            widget_type=curType,
        )
        self._plot_widget.addItem(tag)
        self._insert_sorted_scene_tag(curType.name, tag)

    def addExistingTag(self, data, type):
        tag = self._create_scene_tag(
            time_value=data["time"],
            action=data["action"],
            colors=data["colors"],
            widget_type=type,
        )
        self._plot_widget.addItem(tag)
        self._insert_sorted_scene_tag(type.name, tag)
        # Register the scene tag against its domain counterpart so
        # subsequent TagUpdated/TagRemoved events locate it. The
        # load path calls load_masters and then walks masters to
        # populate scene tags; identities here match domain tags
        # stored in ProjectState.
        domain_tags = self._domain_tag_list(type.name)
        if domain_tags is not None:
            for domain_tag in domain_tags:
                if (
                    float(domain_tag.time_seconds) == float(data["time"])
                    and id(domain_tag) not in self._scene_by_domain_id
                ):
                    self._scene_by_domain_id[id(domain_tag)] = tag
                    break
        return tag

    def editTagTypeOnWave(self, data):
        tags = self._scene_tags.get(data["tagType"], [])
        for tag in tags:
            if data["state"]:
                tag.show()
            else:
                tag.hide()

    # ------------------------------------------------------------------
    # Rubber-band selection
    # ------------------------------------------------------------------

    def install_rubber_band(self):
        """Install rubber-band selection on the plot scene by
        monkey-patching the ViewBox mouse handlers. Preserves the
        originals for delegation when Shift is not held, matching
        the WaveRenderer.wheelEventFixedCenter pattern."""
        vb = self._plot_widget.getViewBox()
        self._orig_vb_mouse_press = vb.mousePressEvent
        self._orig_vb_mouse_move = vb.mouseMoveEvent
        self._orig_vb_mouse_release = vb.mouseReleaseEvent
        vb.mousePressEvent = self._vb_mouse_press
        vb.mouseMoveEvent = self._vb_mouse_move
        vb.mouseReleaseEvent = self._vb_mouse_release

    def _vb_mouse_press(self, ev):
        shift_held = bool(
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        )
        if ev.button() == Qt.MouseButton.LeftButton and shift_held:
            vb = self._plot_widget.getViewBox()
            scene_pos = ev.scenePos()
            view_pos = vb.mapSceneToView(scene_pos)
            self._rubber_band_start_x = float(view_pos.x())
            self._rubber_band_active = True
            self._create_rubber_band_item(
                x0=self._rubber_band_start_x,
                x1=self._rubber_band_start_x,
            )
            ev.accept()
            return
        # Plain left click on empty area: clear selection.
        if ev.button() == Qt.MouseButton.LeftButton and self._selected_tags:
            self.clear_selection()
        if self._orig_vb_mouse_press is not None:
            self._orig_vb_mouse_press(ev)

    def _vb_mouse_move(self, ev):
        if self._rubber_band_active:
            vb = self._plot_widget.getViewBox()
            view_pos = vb.mapSceneToView(ev.scenePos())
            x_now = float(view_pos.x())
            self._update_rubber_band_item(
                x0=self._rubber_band_start_x,
                x1=x_now,
            )
            ev.accept()
            return
        if self._orig_vb_mouse_move is not None:
            self._orig_vb_mouse_move(ev)

    def _vb_mouse_release(self, ev):
        if self._rubber_band_active:
            vb = self._plot_widget.getViewBox()
            view_pos = vb.mapSceneToView(ev.scenePos())
            x_end = float(view_pos.x())
            x0 = min(self._rubber_band_start_x, x_end)
            x1 = max(self._rubber_band_start_x, x_end)
            self._apply_rubber_band_selection(x0, x1)
            self._destroy_rubber_band_item()
            self._rubber_band_active = False
            self._rubber_band_start_x = None
            ev.accept()
            return
        if self._orig_vb_mouse_release is not None:
            self._orig_vb_mouse_release(ev)

    def _create_rubber_band_item(self, x0, x1):
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QBrush, QPen
        from PyQt6.QtGui import QColor as _QColor
        from PyQt6.QtWidgets import QGraphicsRectItem

        vb = self._plot_widget.getViewBox()
        vr = vb.viewRect()
        rect = QRectF(x0, vr.top(), x1 - x0, vr.height())
        item = QGraphicsRectItem(rect)
        brush = QBrush(_QColor(100, 150, 255, 60))
        pen = QPen(_QColor(70, 110, 200))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidth(1)
        pen.setCosmetic(True)
        item.setBrush(brush)
        item.setPen(pen)
        item.setZValue(200)
        self._plot_widget.scene().addItem(item)
        self._rubber_band_item = item

    def _update_rubber_band_item(self, x0, x1):
        if self._rubber_band_item is None:
            return
        from PyQt6.QtCore import QRectF

        vb = self._plot_widget.getViewBox()
        vr = vb.viewRect()
        lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
        self._rubber_band_item.setRect(
            QRectF(lo, vr.top(), hi - lo, vr.height()),
        )

    def _destroy_rubber_band_item(self):
        if self._rubber_band_item is None:
            return
        scene = self._plot_widget.scene()
        if scene is not None:
            scene.removeItem(self._rubber_band_item)
        self._rubber_band_item = None

    def _apply_rubber_band_selection(self, x0, x1):
        """Replace selection with all scene tags whose time falls
        in [x0, x1]."""
        self.clear_selection()
        if x1 <= x0:
            return
        for _type_name, lst in self._scene_tags.items():
            for scene_tag in lst:
                try:
                    tval = float(scene_tag.value())
                except (TypeError, ValueError):
                    continue
                if x0 <= tval <= x1:
                    self._selected_tags.add(scene_tag)
                    self._apply_selection_visual(
                        scene_tag,
                        selected=True,
                    )
