import pyqtgraph as pg

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

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
        self._manager.curType.addTag(tag)
        if (
            self._state is not None
            and self._project_window is not None
            and not self._project_window.is_loading()
        ):
            # NOTE: state appends tags; widget TagType.addTag bisect-inserts
            # by time. Orderings will diverge from this PR onwards —
            # tracked as a followup (see PR description).
            self._state.add_tag(
                self._master_id,
                self._slave_id,
                self._manager.curType.name,
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
        type.addTag(tag)
        return tag

    def editTagTypeOnWave(self, data):
        tags = self._manager.types[data["tagType"]].tags
        for tag in tags:
            if data["state"]:
                tag.show()
            else:
                tag.hide()
