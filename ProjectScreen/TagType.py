class TagType():
    def __init__(self, color, name, pin):
        self.setColor(color)
        self.setName(name)
        self.setPin(pin)

    def setColor(self, color):
        self.color = color

    def setName(self, name):
        self.name = name

    def setPin(self, pin):
        self.pin = pin