from pyqtgraph import  InfiniteLine

class Tag(InfiniteLine):
    def __init__(self, pos=None, angle=90, pen=None, movable=False, bounds=None,
                 hoverPen=None,  name=None):

        super().__init__(pos=pos, angle=angle, pen=pen, movable=movable,
                         bounds=bounds, hoverPen=hoverPen, name=None)
