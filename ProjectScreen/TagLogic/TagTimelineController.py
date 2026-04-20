import bisect
import logging

import pyqtgraph as pg

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from typing import Dict, List

from ProjectScreen.TagLogic.TagObject import Tag
from lightconductor.application.commands import AddTagCommand, MoveTagCommand
from lightconductor.application.project_state import (
    TagAdded,
    TagRemoved,
    TagUpdated,
)
from lightconductor.domain.models import Tag as DomainTag


_SNAP_GRANULARITY_SECONDS = 0.1


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
                did: st
                for did, st in self._scene_by_domain_id.items()
                if st is not tag
            }
        self._scene_tags.pop(type_name, None)

    def remove_scene_tag(self, type_name, tag_item):
        lst = self._scene_tags.get(type_name)
        if lst is not None:
            try:
                lst.remove(tag_item)
            except ValueError:
                pass
        scene = tag_item.scene()
        if scene is not None:
            scene.removeItem(tag_item)
        for did, st in list(self._scene_by_domain_id.items()):
            if st is tag_item:
                del self._scene_by_domain_id[did]
                break

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
            return tuple(int(c) for c in color.split(','))
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
        if tag_info is None:
            return
        if getattr(tag_info, "tag", None) is not scene_tag:
            return
        try:
            new_x = float(scene_tag.value())
        except (TypeError, ValueError):
            return
        scene_tag.time = new_x
        if getattr(tag_info, "tagTimeText", None) is not None:
            tag_info.tagTimeText.setText(f"{new_x:.3f}")

    def _find_domain_id_for_scene_tag(self, scene_tag):
        for did, st in self._scene_by_domain_id.items():
            if st is scene_tag:
                return did
        return None

    def _on_tag_drag_finished(self, scene_tag):
        raw_time = max(0.0, float(scene_tag.value()))
        snapped = round(raw_time / _SNAP_GRANULARITY_SECONDS) * _SNAP_GRANULARITY_SECONDS
        snapped = round(snapped, 6)
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
                    type_name, idx,
                )
                scene_tag.setPos(old_time)
                scene_tag.time = old_time
        else:
            try:
                self._state.update_tag(
                    self._master_id, self._slave_id, type_name,
                    idx, time_seconds=snapped,
                )
            except (KeyError, IndexError):
                scene_tag.setPos(old_time)
                scene_tag.time = old_time

    def _handle_tag_added(self, event):
        domain_tags = self._domain_tag_list(event.type_name)
        if domain_tags is None or event.tag_index >= len(domain_tags):
            logger.warning(
                "TagAdded refers to missing domain tag: type=%s idx=%s",
                event.type_name, event.tag_index,
            )
            return
        domain_tag = domain_tags[event.tag_index]
        widget_type = self._manager.types.get(event.type_name)
        if widget_type is None:
            logger.warning(
                "TagAdded for unknown widget type: %s", event.type_name,
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
                event.type_name, event.tag_index, len(lst),
            )
            return
        scene_tag = lst[event.tag_index]
        scene = scene_tag.scene()
        if scene is not None:
            scene.removeItem(scene_tag)
        del lst[event.tag_index]
        for did, st in list(self._scene_by_domain_id.items()):
            if st is scene_tag:
                del self._scene_by_domain_id[did]
                break

    def _handle_tag_updated(self, event):
        domain_tags = self._domain_tag_list(event.type_name)
        if domain_tags is None or event.tag_index >= len(domain_tags):
            logger.warning(
                "TagUpdated refers to missing domain tag: type=%s idx=%s",
                event.type_name, event.tag_index,
            )
            return
        domain_tag = domain_tags[event.tag_index]
        scene_tag = self._scene_by_domain_id.get(id(domain_tag))
        if scene_tag is None:
            logger.warning(
                "TagUpdated for unknown scene tag: type=%s idx=%s",
                event.type_name, event.tag_index,
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
        if (
            self._project_window is not None
            and self._project_window.is_loading()
        ):
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
