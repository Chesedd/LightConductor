from PyQt6.QtWidgets import QWidget, QSizePolicy, QPushButton, QScrollArea, QVBoxLayout, QFrame
from PyQt6.QtCore import pyqtSignal, Qt

class DropBox(QWidget):
    boxDeleted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mainLayout.setSpacing(0)

        self.createTitleButton()
        self.createContentArea()

        self.mainLayout.addWidget(self.toggleButton)
        self.mainLayout.addWidget(self.contentArea)

    def createTitleButton(self):
        self.toggleButton = QPushButton()
        self.toggleButton.setCheckable(True)
        self.toggleButton.setChecked(False)
        self.toggleButton.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 8px;
                border: 1px solid #ccc;
                background-color: #f0f0f0;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:checked {
                background-color: #d0d0d0;
                border-bottom: none;
            }
        """)
        self.toggleButton.toggled.connect(self.onToggled)

    def createContentArea(self):
        self.contentArea = QScrollArea()
        self.contentArea.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.contentArea.setMaximumHeight(0)
        self.contentArea.setMinimumHeight(0)
        self.contentArea.setFrameShape(QFrame.Shape.NoFrame)
        self.contentArea.setWidgetResizable(True)

        self.contentWidget = QWidget()
        self.contentLayout = QVBoxLayout(self.contentWidget)
        self.contentLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.contentLayout.setSpacing(5)
        self.contentLayout.setContentsMargins(10, 10, 10, 10)
        self.contentArea.setWidget(self.contentWidget)

    def onToggled(self, checked):
        if checked:
            self.toggleButton.setText("► " + self.toggleButton.text()[2:])
            self.contentArea.setMaximumHeight(16777215)
            self.contentArea.setMinimumHeight(400)
        else:
            self.toggleButton.setText("▼ " + self.toggleButton.text()[2:])
            self.contentArea.setMaximumHeight(0)
            self.contentArea.setMinimumHeight(0)