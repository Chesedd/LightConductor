from  PyQt6.QtWidgets import QWidget, QLabel, QLineEdit, QVBoxLayout, QHBoxLayout, QPushButton, QSizePolicy

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

        buttonLayout = QHBoxLayout()
        self.saveButton = QPushButton("Save")
        self.saveButton.clicked.connect(self.editTag)
        self.saveButton.setEnabled(False)
        self.deleteButton = QPushButton("Delete tag")
        self.deleteButton.clicked.connect(self.deleteTag)
        self.deleteButton.setEnabled(False)
        buttonLayout.addWidget(self.saveButton)
        buttonLayout.addWidget(self.deleteButton)

        self.mainLayout.addLayout(tagTypeLayout)
        self.mainLayout.addLayout(tagTimeLayout)
        self.mainLayout.addLayout(tagStateLayout)
        self.mainLayout.addLayout(buttonLayout)

    def setTag(self, tag):
        self.tag = tag
        self.tagTypeText.setText(tag.type.name)
        self.tagTimeText.setText(str(tag.time))
        self.tagTimeText.setEnabled(True)
        self.tagStateText.setText(str(tag.state))
        self.tagStateText.setEnabled(True)
        self.saveButton.setEnabled(True)
        self.deleteButton.setEnabled(True)

    def setNone(self):
        return

    def editTag(self):
        params = {}
        params["time"] = self.tagTimeText.text()
        params["state"] = self.tagStateText.text()
        self.tag.editParams(params)

    def deleteTag(self):
        self.tag.deleteTag()
        self.tagTypeText.setText("")
        self.tagTimeText.setText("")
        self.tagTimeText.setEnabled(False)
        self.tagStateText.setText("")
        self.tagStateText.setEnabled(False)
        self.saveButton.setEnabled(False)
        self.deleteButton.setEnabled(False)