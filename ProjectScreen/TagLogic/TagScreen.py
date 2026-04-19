import logging

from  PyQt6.QtWidgets import QWidget, QLabel, QLineEdit, QVBoxLayout, QHBoxLayout, QPushButton, QButtonGroup
from AssistanceTools.ColorPicker import ColorPicker

logger = logging.getLogger(__name__)

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
                                QPushButton:disabled {
                                    background-color: #2f2f2f;
                                    border: 1px dashed #7a7a7a;
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
                                QPushButton:disabled {
                                    background-color: #2f2f2f;
                                    border: 1px dashed #7a7a7a;
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

        tagTime, tagAction = self.initMainLabels()

        paramsLayout.addWidget(tagTypeWidget)
        paramsLayout.addWidget(self.tagState)
        paramsLayout.addWidget(tagTime)
        paramsLayout.addWidget(tagAction)
        paramsLayout.addWidget(self.initMainButtons())

        self.mainLayout.addWidget(params)
        self.mainLayout.addWidget(self.initColorWidget())

    def initMainLabels(self):
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

        return tagTimeWidget, tagActionWidget

    def initMainButtons(self):
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

        return buttonWidget


    def initColorWidget(self):
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

        return colorPickerWidget

    def setColor(self):
        button = self.buttons.checkedButton()
        if button:
            rgb = [self.colorPicker.rgb[0], self.colorPicker.rgb[1], self.colorPicker.rgb[2]]
            logger.debug("Color picked: %s", rgb)
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
        topology = getattr(tag.type, "topology", [i for i in range(tag.type.row * tag.type.table)])
        color_index_by_cell = {cell: i for i, cell in enumerate(topology)}
        for i in range(tag.type.row):
            row = QWidget()
            rowLayout = QHBoxLayout(row)
            self.tagStateLayout.addWidget(row)
            for j in range(tag.type.table):
                button = ColorButton()
                cell = i * tag.type.table + j
                if cell in color_index_by_cell:
                    color = colors[color_index_by_cell[cell]]
                    button.setColor(color)
                    button.setEnabled(True)
                    button.setText("")
                else:
                    button.setColor([0, 0, 0])
                    button.setEnabled(False)
                    button.setText("·")
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
        topology = getattr(self.tag.type, "topology", [i for i in range(self.tag.type.row * self.tag.type.table)])
        params["colors"] = []
        for cell in topology:
            params["colors"].append(self.buttons.buttons()[cell].rgb)
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
