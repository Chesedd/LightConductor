from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout,
    QCheckBox, QGroupBox, QScrollArea
)
from PyQt6.QtCore import pyqtSignal

class TagTypeChooseBox(QGroupBox):
    stateChanged = pyqtSignal(dict)
    def __init__(self, title):
        super().__init__(title=title)

        self.wave = None
        self.initUI()

    def initUI(self):
        self.scrollArea = QScrollArea()
        self.scrollArea.setWidgetResizable(True)

        self.innerWidget = QWidget()
        self.innerLayout = QVBoxLayout()
        self.innerWidget.setLayout(self.innerLayout)

        self.scrollArea.setWidget(self.innerWidget)

        self.mainLauout = QVBoxLayout()
        self.mainLauout.addWidget(self.scrollArea)
        self.setLayout(self.mainLauout)

    def addType(self, title):
        buttonChecker = QCheckBox(title)
        buttonChecker.toggled.connect(self.onStateChanged)
        buttonChecker.setChecked(True)
        self.innerLayout.addWidget(buttonChecker)

    def onStateChanged(self, checked):
        checkbox = self.sender()
        data = {"state": checked, "tagType": checkbox.text()}
        self.stateChanged.emit(data)