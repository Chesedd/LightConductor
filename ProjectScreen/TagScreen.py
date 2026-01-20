from  PyQt6.QtWidgets import QWidget, QLabel, QLineEdit, QVBoxLayout, QHBoxLayout, QPushButton

class TagInfoScreen(QWidget):
    def __init__(self, tagTypes):
        super().__init__()
        self.tag = None
        self.tagTypes = tagTypes
        self.initUI()

    def initUI(self):
        self.mainLayout = QVBoxLayout()
        self.setLayout(self.mainLayout)

        tagType = QLabel("Tag type:")
        self.tagTypeText = QLabel()
        tagTypeLayout = QHBoxLayout()
        tagTypeLayout.addWidget(tagType)
        tagTypeLayout.addWidget(self.tagTypeText)

        tagTime = QLabel("Tag time:")
        self.tagTimeText = QLineEdit()
        self.tagTimeText.setEnabled(False)
        tagTimeLayout = QHBoxLayout()
        tagTimeLayout.addWidget(tagTime)
        tagTimeLayout.addWidget(self.tagTimeText)

        tagState = QLabel("Tag state:")
        self.tagStateText = QLineEdit()
        self.tagStateText.setEnabled(False)
        tagStateLayout = QHBoxLayout()
        tagStateLayout.addWidget(tagState)
        tagStateLayout.addWidget(self.tagStateText)

        self.saveButton = QPushButton("Save")
        self.saveButton.clicked.connect(self.editTag)
        self.saveButton.setEnabled(False)

        self.mainLayout.addLayout(tagTypeLayout)
        self.mainLayout.addLayout(tagTimeLayout)
        self.mainLayout.addLayout(tagStateLayout)
        self.mainLayout.addWidget(self.saveButton)

    def setTag(self, tag):
        self.tag = tag
        self.tagTypeText.setText(tag.type.name)
        self.tagTimeText.setText(str(tag.time))
        self.tagTimeText.setEnabled(True)
        self.tagStateText.setText(str(tag.state))
        self.tagStateText.setEnabled(True)
        self.saveButton.setEnabled(True)

    def setNone(self):
        return

    def editTag(self):
        params = {}
        params["time"] = self.tagTimeText.text()
        params["state"] = self.tagStateText.text()
        self.tag.editParams(params)