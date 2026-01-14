from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import QAction

class CollapsibleBox(QWidget):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mainLayout.setSpacing(0)

        self.createTitleButton()
        self.createContentArea()

        self.mainLayout.addWidget(self.toggleButton)
        self.mainLayout.addWidget(self.contentArea)

        self.toggleButton.setText("▼ "+title)


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


    def contextMenuEvent(self, a0):
        menu = QMenu(self)

        renameAction = QAction("Rename", self)
        renameAction.triggered.connect(self.showRenameDialog)
        menu.addAction(renameAction)

        deleteAction = QAction("Delete", self)
        deleteAction.triggered.connect(self.showDeleteDialog)
        menu.addAction(deleteAction)

        menu.exec(a0.globalPos())

    def onToggled(self, checked):
        if checked:
            self.toggleButton.setText("► " + self.toggleButton.text()[2:])
            self.contentArea.setMaximumHeight(16777215)
            self.contentArea.setMinimumHeight(0)
        else:
            self.toggleButton.setText("▼ " + self.toggleButton.text()[2:])
            self.contentArea.setMaximumHeight(0)

    def addWidget(self, widget):
        self.contentLayout.addWidget(widget)

    def removeWidget(self, widget):
        self.contentLayout.removeWidget(widget)
        widget.setParent(None)

    def clear(self):
        while self.contentLayout.count():
            child = self.contentLayout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def showRenameDialog(self):
        dialog = RenameDialog(self)
        dialog.boxRenamed.connect(self.renameBox)
        dialog.exec()

    def renameBox(self, newTitle):
        self.toggleButton.setText("▼ " + newTitle)

    def showDeleteDialog(self):
        dialog = DeleteDialog(self)
        dialog.boxDelete.connect(self.deleteBox)
        dialog.exec()

    def deleteBox(self):
        self.deleteLater()

class RenameDialog(QDialog):
    boxRenamed = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Rename box")
        newNameText = QLabel("Insert new title")
        self.newNameBar = QLineEdit()
        self.newNameParams = QWidget()
        newNameLayout = QHBoxLayout(self.newNameParams)
        newNameLayout.addWidget(newNameText)
        newNameLayout.addWidget(self.newNameBar)

        self.buttons = QWidget()
        buttonsLayout = QHBoxLayout(self.buttons)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.on_ok_clicked)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttonsLayout.addWidget(ok_btn)
        buttonsLayout.addWidget(cancel_btn)

        self.mainLayout = QVBoxLayout()
        self.mainLayout.addWidget(self.newNameParams)
        self.mainLayout.addWidget(self.buttons)
        self.setLayout(self.mainLayout)

    def on_ok_clicked(self):
        self.boxRenamed.emit(self.newNameBar.text())
        self.accept()

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
        ok_btn.clicked.connect(self.on_ok_clicked)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttonsLayout.addWidget(ok_btn)
        buttonsLayout.addWidget(cancel_btn)

        self.mainLayout = QVBoxLayout()
        self.mainLayout.addWidget(newNameText)
        self.mainLayout.addWidget(self.buttons)
        self.setLayout(self.mainLayout)

    def on_ok_clicked(self):
        self.boxDelete.emit()
        self.accept()