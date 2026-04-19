import pyqtgraph as pg

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from ProjectScreen.TagLogic.TagObject import Tag


class TagTimelineController:
    def __init__(self, plot_widget, manager, renderer):
        self._plot_widget = plot_widget
        self._manager = manager
        self._renderer = renderer

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
