import bisect
class TagType():
    def __init__(self, color, name, pin):
        self.setColor(color)
        self.setName(name)
        self.setPin(pin)
        self.tags = []

    def setColor(self, color):
        self.color = color

    def setName(self, name):
        self.name = name

    def setPin(self, pin):
        self.pin = pin

    def addTag(self, tag):
        index = bisect.bisect_left([t.time for t in self.tags], tag.time)
        self.tags.insert(index, tag)

    def addExistingTags(self, tags):
        self.tags = tags