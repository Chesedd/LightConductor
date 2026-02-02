from  PyQt6.QtWidgets import QWidget, QLabel, QLineEdit, QVBoxLayout, QHBoxLayout, QPushButton, QButtonGroup
from AssistanceTools.ColorPicker import ColorPicker

class ColorButton(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.rgb = [0, 0, 0]
        self.setStyleSheet("""
                                QPushButton {
                                    background-color: black;
                                }
                                QPushButton:checked {
                                    border: 2px solid #ff9900; 
                                    padding: 11px;
                                }
                            """)


    def setColor(self, rgb):
        self.rgb = rgb
        self.setStyleSheet("""
                                QPushButton {
                                """
                                    f"background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]});"
                                """
                                }
                                QPushButton:checked {
                                    border: 2px solid #ff9900; 
                                    padding: 11px;
                                }
                            """)

class TagInfoScreen(QWidget):
    def __init__(self, tagTypes):
        super().__init__()
        self.tag = None
        self.tagTypes = tagTypes
        self.buttons = QButtonGroup()
        self.initUI()

    def initUI(self):
        self.mainLayout = QHBoxLayout()
        self.setLayout(self.mainLayout)

        params = QWidget()
        paramsLayout = QVBoxLayout(params)

        tagType = QLabel("Tag type:")
        self.tagTypeText = QLabel()
        tagTypeWidget = QWidget()
        tagTypeLayout = QHBoxLayout(tagTypeWidget)
        tagTypeLayout.addWidget(tagType)
        tagTypeLayout.addWidget(self.tagTypeText)

        self.tagState = QWidget()
        self.tagStateLayout = QVBoxLayout(self.tagState)

        tagTime = QLabel("Tag time:")
        self.tagTimeText = QLineEdit()
        self.tagTimeText.setEnabled(False)
        tagTimeWidget = QWidget()
        tagTimeLayout = QHBoxLayout(tagTimeWidget)
        tagTimeLayout.addWidget(tagTime)
        tagTimeLayout.addWidget(self.tagTimeText)

        tagAction = QLabel("Tag action:")
        self.tagActionText = QLineEdit()
        self.tagActionText.setEnabled(False)
        tagActionWidget = QWidget()
        tagActionLayout = QHBoxLayout(tagActionWidget)
        tagActionLayout.addWidget(tagAction)
        tagActionLayout.addWidget(self.tagActionText)

        buttonWidget = QWidget()
        buttonLayout = QHBoxLayout(buttonWidget)
        self.saveButton = QPushButton("Save")
        self.saveButton.clicked.connect(self.editTag)
        self.saveButton.setEnabled(False)
        self.deleteButton = QPushButton("Delete tag")
        self.deleteButton.clicked.connect(self.deleteTag)
        self.deleteButton.setEnabled(False)
        buttonLayout.addWidget(self.saveButton)
        buttonLayout.addWidget(self.deleteButton)

        paramsLayout.addWidget(tagTypeWidget)
        paramsLayout.addWidget(self.tagState)
        paramsLayout.addWidget(tagTimeWidget)
        paramsLayout.addWidget(tagActionWidget)
        paramsLayout.addWidget(buttonWidget)

        colorPickerWidget = QWidget()
        colorPickerLayout = QVBoxLayout(colorPickerWidget)

        self.colorPicker = ColorPicker()
        setButton = QPushButton("Set color")
        setButton.clicked.connect(self.setColor)
        dropButton = QPushButton("Drop color")
        dropButton.clicked.connect(self.dropColor)

        colorButtons = QWidget()
        colorButtonsLayout = QHBoxLayout(colorButtons)
        colorButtonsLayout.addWidget(setButton)
        colorButtonsLayout.addWidget(dropButton)

        colorPickerLayout.addWidget(self.colorPicker)
        colorPickerLayout.addWidget(colorButtons)

        self.mainLayout.addWidget(params)
        self.mainLayout.addWidget(colorPickerWidget)

    def setColor(self):
        button = self.buttons.checkedButton()
        if button:
            rgb = [self.colorPicker.rgb[0], self.colorPicker.rgb[1], self.colorPicker.rgb[2]]
            print(rgb)
            button.setColor(rgb)

    def dropColor(self):
        button = self.buttons.checkedButton()
        if button:
            rgb = [0, 0, 0]
            button.setColor(rgb)

    def setTag(self, tag):
        self.tag = tag
        self.tagTypeText.setText(tag.type.name)
        self.tagTimeText.setText(str(tag.time))
        self.tagTimeText.setEnabled(True)
        self.tagActionText.setText(str(tag.action))
        self.tagActionText.setEnabled(True)
        self.saveButton.setEnabled(True)
        self.deleteButton.setEnabled(True)

        colors = tag.colors
        self.deleteAllWidgets(self.tagStateLayout)
        for i in range(tag.type.row):
            row = QWidget()
            rowLayout = QHBoxLayout(row)
            self.tagStateLayout.addWidget(row)
            for j in range(tag.type.table):
                button = ColorButton()
                button.setColor(colors[i*tag.type.table + j])
                print(colors[i*tag.type.table + j])
                button.setFixedSize(20, 20)
                button.setCheckable(True)
                self.buttons.addButton(button)
                rowLayout.addWidget(button)
            self.tagStateLayout.addWidget(row)


    def deleteAllWidgets(self, layout):
        if layout is None:
            return

        while layout.count():
            item = layout.takeAt(0)

            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

            elif item.layout() is not None:
                self.deleteAllWidgets(item.layout())
    def setNone(self):
        return

    def editTag(self):
        params = {}
        params["time"] = self.tagTimeText.text()
        params["action"] = self.tagActionText.text()
        params["colors"] = [button.rgb for button in self.buttons.buttons()]
        self.tag.editParams(params)

    def deleteTag(self):
        self.tag.deleteTag()
        self.deleteAllWidgets(self.tagStateLayout)
        self.tagTypeText.setText("")
        self.tagTimeText.setText("")
        self.tagTimeText.setEnabled(False)
        self.tagActionText.setText("")
        self.tagActionText.setEnabled(False)
        self.saveButton.setEnabled(False)
        self.deleteButton.setEnabled(False)