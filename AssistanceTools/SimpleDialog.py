from PyQt6.QtWidgets import QDialog, QLabel, QLineEdit, QHBoxLayout, QWidget, QPushButton


class SimpleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

    #создание виджета вида: текст+лайн
    def LabelAndLine(self, text):
        label = QLabel(text)
        line = QLineEdit()
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.addWidget(label)
        layout.addWidget(line)
        self.layout().addWidget(widget)
        return line

    #создание виджета вида: ok+cancel
    def OkAndCancel(self):
        okBtn = QPushButton("OK")
        cancelBtn = QPushButton("Cancel")
        cancelBtn.clicked.connect(self.reject)
        buttons = QWidget()
        buttonsLayout = QHBoxLayout(buttons)
        buttonsLayout.addWidget(okBtn)
        buttonsLayout.addWidget(cancelBtn)
        self.layout().addWidget(buttons)
        return okBtn
