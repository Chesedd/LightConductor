import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout,
    QHBoxLayout, QCheckBox, QGroupBox
)
from PyQt6.QtCore import pyqtSignal

class TagTypeChooseBox(QGroupBox):
    stateChanged = pyqtSignal(dict)
    def __init__(self, title):
        super().__init__(title=title)
        self.wave = None
        self.mainLauout = QVBoxLayout()
        self.setLayout(self.mainLauout)

    def addType(self, title):
        buttonChecker = QCheckBox(title)
        buttonChecker.toggled.connect(self.onStateChanged)
        buttonChecker.setChecked(True)
        self.mainLauout.addWidget(buttonChecker)

    def onStateChanged(self, checked):
        checkbox = self.sender()
        data = {"state": checked, "tagType": checkbox.text()}
        self.stateChanged.emit(data)