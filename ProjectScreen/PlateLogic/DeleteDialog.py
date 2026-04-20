from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DeleteDialog(QDialog):
    boxDelete = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Delete box")
        newNameText = QLabel("Are you sure?")

        self.buttons = QWidget()
        buttonsLayout = QHBoxLayout(self.buttons)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.onOkClicked)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttonsLayout.addWidget(ok_btn)
        buttonsLayout.addWidget(cancel_btn)

        self.mainLayout = QVBoxLayout()
        self.mainLayout.addWidget(newNameText)
        self.mainLayout.addWidget(self.buttons)
        self.setLayout(self.mainLayout)

    def onOkClicked(self):
        self.boxDelete.emit()
        self.accept()
