from PyQt6.QtWidgets import QLayout, QWidgetItem, QSizePolicy
from PyQt6.QtCore import Qt, QRect, QSize, QPoint

class FlowLayout(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.itemList = []
        self.hSpacing = 6
        self.vSpacing = 6

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def insertWidget(self, index, widget):
        if index < 0 or index > len(self.itemList):
            index = len(self.itemList)

        item = QWidgetItem(widget)
        self.itemList.insert(index, item)

        if widget.parent() is None and self.parentWidget():
            widget.setParent(self.parentWidget())

        self.invalidate()
        if self.parentWidget():
            widget.show()
            self.parentWidget().updateGeometry()
            self.parentWidget().update()
        return index
    def addItem(self, item):
        self.itemList.append(item)

    def horizontalSpacing(self):
        return self.hSpacing

    def verticalSpacing(self):
        return self.vSpacing

    def setHorizontalSpacing(self, spacing):
        self.hSpacing = spacing

    def setVerticalSpacing(self, spacing):
        self.vSpacing = spacing

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._doLayout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        size+=QSize(left + right, top + bottom)
        return size
    def _doLayout(self, rect, testOnly):
        left, top, right, bottom = self.getContentsMargins()
        effectiveRect = rect.adjusted(left, top, -right, -bottom)
        x = effectiveRect.x()
        y = effectiveRect.y()
        lineHeight = 0

        for item in self.itemList:
            widget = item.widget()
            if widget is None:
                continue

            spaceX = self.horizontalSpacing()
            if spaceX == -1:
                spaceX = widget.style().layoutSpacing(
                    QSizePolicy.ControlType.PushButton,
                    QSizePolicy.ControlType.PushButton, Qt.Orientation.Horizontal)

            spaceY = self.verticalSpacing()
            if spaceY == -1:
                spaceY = widget.style().layoutSpacing(
                    QSizePolicy.ControlType.PushButton,
                    QSizePolicy.ControlType.PushButton, Qt.Orientation.Vertical)
            
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > effectiveRect.right() and lineHeight > 0:
                x = effectiveRect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y() + bottom
