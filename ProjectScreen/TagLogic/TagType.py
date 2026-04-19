import bisect
import logging

logger = logging.getLogger(__name__)


class TagType():
    def __init__(self, color, name, pin, row, table, topology=None):
        self.setColor(color)
        self.setName(name)
        self.setPin(pin)  # legacy field name, now stores segment start index
        self.setRow(row)
        self.setTable(table)
        self.setTopology(topology)
        self.tags = []

    def setRow(self, row):
        self.row = row

    def setTable(self, table):
        self.table = table

    def setColor(self, color):
        self.color = color

    def setName(self, name):
        self.name = name

    def setPin(self, pin):
        self.pin = pin

    def setTopology(self, topology):
        if topology is None:
            self.topology = [i for i in range(self.row * self.table)]
        else:
            self.topology = topology

    @property
    def segment_start(self):
        return self.pin

    def addTag(self, tag):
        index = bisect.bisect_left([t.time for t in self.tags], tag.time)
        self.tags.insert(index, tag)

    def editTag(self):
        self.tags.sort(key=lambda tag: tag.time)

    def addExistingTags(self, tags):
        self.tags = tags

    def deleteTag(self, tag):
        self.tags.remove(tag)
        logger.debug("Tags after deletion: %s", self.tags)
