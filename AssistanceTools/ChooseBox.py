import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout,
    QHBoxLayout, QCheckBox, QGroupBox
)

class TagTypeChooseBox(QGroupBox):
    def __init__(self, title):
        super().__init__(title=title)
        self.mainLauout = QVBoxLayout()
        self.setLayout(self.mainLauout)

    def addType(self, title):
        buttonChecker = QCheckBox(title)
        self.mainLauout.addWidget(buttonChecker)