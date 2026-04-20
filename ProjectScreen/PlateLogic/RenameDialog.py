from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from AssistanceTools.SimpleDialog import SimpleDialog


class RenameDialog(SimpleDialog):
    boxRenamed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        self.mainLayout = QVBoxLayout(self)

        self.setWindowTitle("Rename box")
        newNameText = QLabel("Insert new title")
        self.newNameBar = QLineEdit()
        self.newNameParams = QWidget()
        newNameLayout = QHBoxLayout(self.newNameParams)
        newNameLayout.addWidget(newNameText)
        newNameLayout.addWidget(self.newNameBar)
        self.mainLayout.addWidget(self.newNameParams)

        okBtn = self.OkAndCancel()
        okBtn.clicked.connect(self.onOkClicked)

    def onOkClicked(self):
        self.boxRenamed.emit(self.newNameBar.text())
        self.accept()
