class TagType:
    def __init__(self, color, name, pin, row, table, topology=None):
        self.setColor(color)
        self.setName(name)
        self.setPin(pin)  # legacy field name, now stores segment start index
        self.setRow(row)
        self.setTable(table)
        self.setTopology(topology)
        # master_id / slave_id are set by TagManager.addType AFTER
        # construction. They are lookup keys for ProjectState only;
        # do NOT use them in widget logic.
        self.master_id: str | None = None
        self.slave_id: str | None = None

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
