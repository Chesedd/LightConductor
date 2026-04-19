import bisect

import pyqtgraph as pg

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from typing import Dict, List

from ProjectScreen.TagLogic.TagObject import Tag
from lightconductor.domain.models import Tag as DomainTag


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
    ):
        self._plot_widget = plot_widget
        self._manager = manager
        self._renderer = renderer
        self._state = state
        self._project_window = project_window
        self._master_id = master_id
        self._slave_id = slave_id
        self._scene_tags: Dict[str, List[Tag]] = {}

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

    def addTag(self, data):
        self.addTagAtTime(data, self._renderer.selectedLine.pos().x())

    def addTagAtTime(self, data, time):
        color = self._manager.curType.color
        r, g, b = map(int, color.split(','))
        tag = Tag(
            pos=QPointF(time, 0.0),
            angle=90,
            pen=pg.mkPen(QColor(r, g, b), width=3),
            action=data["action"],
            colors=data["colors"],
            type=self._manager.curType,
            manager=self._manager,
        )
        self._plot_widget.addItem(tag)
        type_name = self._manager.curType.name
        self._insert_sorted_scene_tag(type_name, tag)
        if (
            self._state is not None
            and self._project_window is not None
            and not self._project_window.is_loading()
        ):
            # State and scene share the sort-by-time invariant: state
            # bisect-inserts internally, and the scene registry above
            # has also bisect-inserted, so indices line up.
            self._state.add_tag(
                self._master_id,
                self._slave_id,
                type_name,
                DomainTag(
                    time_seconds=float(time),
                    action=data["action"],
                    colors=list(data["colors"]),
                ),
            )

    def addExistingTag(self, data, type):
        color = type.color
        r, g, b = map(int, color.split(','))
        tag = Tag(pos=QPointF(data["time"], 0.0), angle=90, pen=pg.mkPen(QColor(r, g, b), width=3), action=data["action"], colors=data["colors"], type = type, manager = self._manager)
        self._plot_widget.addItem(tag)
        self._insert_sorted_scene_tag(type.name, tag)
        return tag

    def editTagTypeOnWave(self, data):
        tags = self._scene_tags.get(data["tagType"], [])
        for tag in tags:
            if data["state"]:
                tag.show()
            else:
                tag.hide()
