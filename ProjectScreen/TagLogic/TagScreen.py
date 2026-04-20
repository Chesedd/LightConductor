import logging

from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from AssistanceTools.ColorPicker import ColorPicker
from lightconductor.application.commands import EditTagCommand

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
        self.setStyleSheet(
            """
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
                            """
        )


class TagInfoScreen(QWidget):
    def __init__(self, state, master_id, slave_id, wave, commands=None):
        super().__init__()
        self._state = state
        self._master_id = master_id
        self._slave_id = slave_id
        self._wave = wave
        self._commands = commands
        self.tag = None
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
            rgb = [
                self.colorPicker.rgb[0],
                self.colorPicker.rgb[1],
                self.colorPicker.rgb[2],
            ]
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
        self.tagActionText.setText("On" if tag.action else "Off")
        self.tagActionText.setEnabled(True)
        self.saveButton.setEnabled(True)
        self.deleteButton.setEnabled(True)

        colors = tag.colors
        self.deleteAllWidgets(self.tagStateLayout)
        topology = getattr(
            tag.type, "topology", [i for i in range(tag.type.row * tag.type.table)]
        )
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
        action_text = self.tagActionText.text().strip().lower()
        params["action"] = action_text in ("on", "true", "1")
        topology = getattr(
            self.tag.type,
            "topology",
            [i for i in range(self.tag.type.row * self.tag.type.table)],
        )
        params["colors"] = []
        for cell in topology:
            params["colors"].append(self.buttons.buttons()[cell].rgb)
        type_ = self.tag.type
        type_name = type_.name if type_ is not None else None
        controller = getattr(self._wave, "_tagController", None)
        # State-first edit: mutate state, then the TagUpdated listener
        # on the controller updates the scene tag's fields and resorts
        # the scene registry. If no state is wired, fall back to
        # mutating the scene tag directly to preserve the legacy path.
        if (
            self._state is not None
            and controller is not None
            and type_ is not None
            and type_name is not None
            and type_.master_id is not None
            and type_.slave_id is not None
        ):
            try:
                idx = controller.scene_tags_for(type_name).index(self.tag)
            except ValueError:
                idx = None
            if idx is not None:
                try:
                    if self._commands is not None:
                        self._commands.push(
                            EditTagCommand(
                                master_id=type_.master_id,
                                slave_id=type_.slave_id,
                                type_name=type_name,
                                tag_index=idx,
                                new_time_seconds=float(params["time"]),
                                new_action=bool(params["action"]),
                                new_colors=list(params["colors"]),
                            )
                        )
                    else:
                        self._state.update_tag(
                            type_.master_id,
                            type_.slave_id,
                            type_name,
                            idx,
                            time_seconds=float(params["time"]),
                            action=bool(params["action"]),
                            colors=list(params["colors"]),
                        )
                    return
                except (KeyError, IndexError):
                    logger.warning(
                        "state update_tag failed: type=%s idx=%s",
                        type_name,
                        idx,
                    )
        self.tag.editParams(params)
        if controller is not None and type_name is not None:
            controller.resort_scene_tags(type_name)

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
