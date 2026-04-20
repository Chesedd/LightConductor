import logging

import pyqtgraph as pg
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from AssistanceTools.ColorPicker import ColorPicker
from AssistanceTools.FlowLayout import FlowLayout
from AssistanceTools.SimpleDialog import SimpleDialog
from lightconductor.application.commands import (
    AddTagTypeCommand,
    DeleteTagTypeCommand,
    EditRangeCommand,
)
from lightconductor.application.project_state import (
    TagTypeAdded,
    TagTypeRemoved,
    TagTypeUpdated,
)
from lightconductor.application.range_allocator import available_starts
from lightconductor.domain.models import TagType as DomainTagType
from ProjectScreen.PlateLogic.DeleteDialog import DeleteDialog
from ProjectScreen.TagLogic.TagType import TagType

logger = logging.getLogger(__name__)


class TagManager(QWidget):
    newTypeCreate = pyqtSignal(TagType)

    def __init__(
        self,
        checkBox,
        state=None,
        project_window=None,
        master_id=None,
        slave_id=None,
        commands=None,
    ):
        super().__init__()
        self.checkBox = checkBox
        self.buttons = QButtonGroup()
        self.buttons.setExclusive(True)
        self.curType = None
        self.types = {}
        self.box = None
        self.tagScreen = None
        self._state = state
        self._project_window = project_window
        self._master_id = master_id
        self._slave_id = slave_id
        self._commands = commands

        self.initPanel()

        self._unsubscribe = None
        if self._state is not None:
            self._unsubscribe = self._state.subscribe(self._on_state_event)

    def initPanel(self):
        self.mainWidget = QWidget()
        self.mainLayout = QVBoxLayout(self.mainWidget)
        self.setLayout(self.mainLayout)

        self.scrollArea = QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setMaximumHeight(200)
        self.innerWidget = QWidget()
        self.innerArea = FlowLayout()
        self.innerWidget.setLayout(self.innerArea)
        self.scrollArea.setWidget(self.innerWidget)

        addButton = QPushButton("+ Add range")
        addButton.clicked.connect(self.showNewTypeDialog)
        self.innerArea.addWidget(addButton)
        self.mainLayout.addWidget(self.scrollArea)

    def showNewTypeDialog(self):
        led_count = self.box.ledCount if self.box else 0
        dialog = newTypeDialog(
            self, led_count=led_count, occupied_ranges=self.getOccupiedRanges()
        )
        dialog.newType.connect(self.addType)
        dialog.exec()

    def getOccupiedRanges(self):
        ranges = []
        for tag_type in self.types.values():
            try:
                start = int(tag_type.pin)
            except ValueError:
                start = 0
            size = int(tag_type.row) * int(tag_type.table)
            ranges.append((start, size))
        return ranges

    def addType(self, params):
        # State-first for user actions: mutate ProjectState and let the
        # TagTypeAdded listener build the widgets. Load-path and
        # headless (no state) fall back to direct widget construction
        # because state is either already populated by load_masters or
        # unavailable entirely.
        if self._state is None or self._project_window is None:
            return self._build_widgets_for_type(params)
        if self._project_window.is_loading():
            return self._build_widgets_for_type(params)
        slave = self._state.master(self._master_id).slaves[self._slave_id]
        if params["name"] in slave.tag_types:
            return self._build_widgets_for_type(params)
        domain_tt = DomainTagType(
            name=params["name"],
            pin=str(params["pin"]),
            rows=int(params["row"]),
            columns=int(params["table"]),
            color=params["color"],
            topology=list(params.get("topology") or []),
            tags=[],
        )
        if self._commands is not None:
            self._commands.push(
                AddTagTypeCommand(
                    master_id=self._master_id,
                    slave_id=self._slave_id,
                    tag_type=domain_tt,
                )
            )
        else:
            self._state.add_tag_type(
                self._master_id,
                self._slave_id,
                domain_tt,
            )
        return self.types.get(params["name"])

    def _build_widgets_for_type(self, params):
        """Build the widget-side TagType + TagButton, register in
        chooseBox, and emit newTypeCreate. Pure widget layer, no state."""
        newType = TagType(
            params["color"],
            params["name"],
            params["pin"],
            params["row"],
            params["table"],
            params.get("topology"),
        )
        self.types[params["name"]] = newType
        button = TagButton(newType, manager=self)
        button.setCheckable(True)
        button.clicked.connect(self.setNewType)
        self.buttons.addButton(button)
        self.innerArea.insertWidget(0, button)
        self.checkBox.addType(params["name"])
        self.newTypeCreate.emit(newType)
        # IDs attached so TagObject.deleteTag can locate the domain tag.
        newType.master_id = self._master_id
        newType.slave_id = self._slave_id
        return newType

    def _on_state_event(self, event):
        if self._master_id is None or self._slave_id is None:
            return
        if getattr(event, "master_id", None) != self._master_id:
            return
        if getattr(event, "slave_id", None) != self._slave_id:
            return
        if isinstance(event, TagTypeAdded):
            self._handle_tag_type_added(event)
        elif isinstance(event, TagTypeRemoved):
            self._handle_tag_type_removed(event)
        elif isinstance(event, TagTypeUpdated):
            self._handle_tag_type_updated(event)

    def _handle_tag_type_added(self, event):
        if event.type_name in self.types:
            return
        try:
            domain_tt = (
                self._state.master(self._master_id)
                .slaves[self._slave_id]
                .tag_types[event.type_name]
            )
        except KeyError:
            logger.warning(
                "TagTypeAdded for missing domain type: %s",
                event.type_name,
            )
            return
        params = {
            "name": domain_tt.name,
            "color": domain_tt.color,
            "pin": domain_tt.pin,
            "row": int(domain_tt.rows),
            "table": int(domain_tt.columns),
            "topology": list(domain_tt.topology),
        }
        self._build_widgets_for_type(params)

    def _handle_tag_type_removed(self, event):
        type_name = event.type_name
        if type_name not in self.types:
            logger.warning(
                "TagTypeRemoved for unknown widget type: %s",
                type_name,
            )
            return
        wave = self.box.wave if self.box is not None else None
        controller = getattr(wave, "_tagController", None)
        if controller is not None:
            controller.remove_scene_tag_type(type_name)
        for btn in list(self.buttons.buttons()):
            if (
                getattr(btn, "tagType", None) is not None
                and btn.tagType.name == type_name
            ):
                self.buttons.removeButton(btn)
                btn.deleteLater()
        # TagTypeChooseBox has no removeType yet; drop matching checkbox
        # directly. TODO: consolidate into ChooseBox.removeType in 3.1b.3.
        inner = getattr(self.checkBox, "innerLayout", None)
        if inner is not None:
            for i in range(inner.count()):
                item = inner.itemAt(i)
                w = item.widget() if item is not None else None
                if isinstance(w, QCheckBox) and w.text() == type_name:
                    w.deleteLater()
                    break
        if self.box is not None:
            states = self.box.tagsLayout
            for i in range(states.count()):
                item = states.itemAt(i)
                st = item.widget() if item is not None else None
                if (
                    st is not None
                    and getattr(st, "tagType", None) is not None
                    and st.tagType.name == type_name
                ):
                    st.deleteLater()
        self.types.pop(type_name, None)
        if self.curType is not None and self.curType.name == type_name:
            self.curType = None

    def _handle_tag_type_updated(self, event):
        type_name = event.type_name
        tt = self.types.get(type_name)
        if tt is None:
            logger.warning(
                "TagTypeUpdated for unknown widget type: %s",
                type_name,
            )
            return
        try:
            domain_tt = (
                self._state.master(self._master_id)
                .slaves[self._slave_id]
                .tag_types[type_name]
            )
        except KeyError:
            logger.warning(
                "TagTypeUpdated for missing domain type: %s",
                type_name,
            )
            return
        tt.pin = domain_tt.pin
        tt.color = domain_tt.color
        for btn in self.buttons.buttons():
            if getattr(btn, "tagType", None) is tt:
                btn.editButton()
                break
        color = domain_tt.color
        if isinstance(color, str):
            r, g, b = map(int, color.split(","))
        else:
            r, g, b = color[:3]
        wave = self.box.wave if self.box is not None else None
        controller = getattr(wave, "_tagController", None)
        if controller is not None:
            for tag in controller.scene_tags_for(type_name):
                tag.setPen(pg.mkPen(QColor(int(r), int(g), int(b)), width=1))

    def setNewType(self):
        self.curType = self.buttons.checkedButton().tagType


class editDialog(SimpleDialog):
    editType = pyqtSignal(dict)

    def __init__(self, parent=None, tagType=None):
        super().__init__(parent=parent)
        self.type = tagType
        self.setWindowTitle(self.type.name)
        self.mainLayout = QVBoxLayout(self)
        self.initParams()

    def initParams(self):
        self.newNameBar = self.LabelAndLine("Name")

        self.colorPicker = ColorPicker()
        color = self.type.color
        rgb = list(map(int, color.split(",")))
        for i in range(3):
            self.colorPicker.slidersLabels[i][0].setValue(rgb[i])
        self.layout().addWidget(self.colorPicker)

        self.newPinBar = self.LabelAndLine("Segment start")

        okBtn = self.OkAndCancel()
        okBtn.clicked.connect(self.onOkClicked)

    def onOkClicked(self):
        params = {
            "name": self.newNameBar.text(),
            "color": f"{self.colorPicker.rgb[0]}, {self.colorPicker.rgb[1]}, {self.colorPicker.rgb[2]}",  # noqa: E501
            "pin": self.newPinBar.text(),
        }
        self.editType.emit(params)
        self.accept()


class newTypeDialog(SimpleDialog):
    newType = pyqtSignal(dict)

    def __init__(self, parent=None, led_count=0, occupied_ranges=None):
        super().__init__(parent=parent)
        self.setWindowTitle("New range")
        self.led_count = led_count
        self.occupied_ranges = occupied_ranges or []
        self.mainLayout = QVBoxLayout(self)
        self.initParams()

    def initParams(self):
        self.newNameBar = self.LabelAndLine("Name")

        self.colorPicker = ColorPicker()
        self.layout().addWidget(self.colorPicker)

        self.rangeLengthBar = self.LabelAndLine("Range length")
        self.rangeLengthBar.setText("1")
        self.rowsBar = self.LabelAndLine("Grid rows")
        self.rowsBar.setText("1")
        self.columnsBar = self.LabelAndLine("Grid columns")
        self.columnsBar.setText("1")

        self.topology = None
        topologyButton = QPushButton("Configure topology")
        topologyButton.clicked.connect(self.configureTopology)
        self.layout().addWidget(topologyButton)

        self.rangeStartLabel = QLabel("Range start")
        self.rangeStartCombo = QComboBox()
        rangeStartWidget = QWidget()
        rangeStartLayout = QHBoxLayout(rangeStartWidget)
        rangeStartLayout.addWidget(self.rangeStartLabel)
        rangeStartLayout.addWidget(self.rangeStartCombo)
        self.layout().addWidget(rangeStartWidget)

        self.rangeLengthBar.textChanged.connect(self.refreshStartChoices)
        self.refreshStartChoices()

        okBtn = self.OkAndCancel()
        okBtn.clicked.connect(self.onOkClicked)

    def refreshStartChoices(self):
        try:
            length = int(self.rangeLengthBar.text())
        except ValueError:
            length = 1
        starts = available_starts(self.led_count, self.occupied_ranges, length)
        if not starts and self.led_count == 0:
            starts = [0]
        self.rangeStartCombo.clear()
        self.rangeStartCombo.addItems([str(start) for start in starts])

    def onOkClicked(self):
        try:
            length = int(self.rangeLengthBar.text())
        except ValueError:
            length = 1
        try:
            rows = int(self.rowsBar.text())
        except ValueError:
            rows = 1
        try:
            cols = int(self.columnsBar.text())
        except ValueError:
            cols = 1
        if rows <= 0:
            rows = 1
        if cols <= 0:
            cols = 1
        max_leds_in_grid = rows * cols
        if length > max_leds_in_grid:
            length = max_leds_in_grid
        start = self.rangeStartCombo.currentText() or "0"
        topology = self.topology
        if topology is None or len(topology) != length:
            topology = [i for i in range(length)]
        params = {
            "name": self.newNameBar.text(),
            "color": f"{self.colorPicker.rgb[0]}, {self.colorPicker.rgb[1]}, {self.colorPicker.rgb[2]}",  # noqa: E501
            "pin": start,
            "row": rows,
            "table": cols,
            "topology": topology,
        }
        self.newType.emit(params)
        self.accept()

    def configureTopology(self):
        try:
            length = int(self.rangeLengthBar.text())
        except ValueError:
            length = 1
        try:
            rows = int(self.rowsBar.text())
        except ValueError:
            rows = 1
        try:
            cols = int(self.columnsBar.text())
        except ValueError:
            cols = 1

        dialog = TopologyDialog(
            rows=max(1, rows),
            cols=max(1, cols),
            led_count=max(1, length),
            order=self.topology,
            parent=self,
        )
        if dialog.exec():
            self.topology = dialog.order


class TopologyDialog(QDialog):
    def __init__(self, rows, cols, led_count, order=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Range topology")
        self.rows = rows
        self.cols = cols
        self.led_count = led_count
        self.order = list(order) if order else []
        if len(self.order) > self.led_count:
            self.order = self.order[: self.led_count]
        self.buttons = {}

        layout = QVBoxLayout(self)
        self.counterLabel = QLabel("")
        layout.addWidget(self.counterLabel)
        gridWidget = QWidget()
        gridLayout = QVBoxLayout(gridWidget)
        for r in range(self.rows):
            rowWidget = QWidget()
            rowLayout = QHBoxLayout(rowWidget)
            for c in range(self.cols):
                index = r * self.cols + c
                btn = QPushButton("")
                btn.setCheckable(True)
                btn.setFixedSize(36, 36)
                btn.clicked.connect(lambda checked, i=index: self.toggleCell(i))
                self.buttons[index] = btn
                rowLayout.addWidget(btn)
            gridLayout.addWidget(rowWidget)
        layout.addWidget(gridWidget)

        okBtn = QPushButton("OK")
        okBtn.clicked.connect(self.accept)
        self.okBtn = okBtn
        layout.addWidget(okBtn)

        self.syncButtons()

    def toggleCell(self, index):
        if index in self.order:
            self.order.remove(index)
        else:
            if len(self.order) >= self.led_count:
                return
            self.order.append(index)
        self.syncButtons()

    def syncButtons(self):
        for index, btn in self.buttons.items():
            if index in self.order:
                position = self.order.index(index)
                btn.setChecked(True)
                btn.setText(str(position))
            else:
                btn.setChecked(False)
                btn.setText("")
        self.counterLabel.setText(f"Selected LEDs: {len(self.order)}/{self.led_count}")
        self.okBtn.setEnabled(len(self.order) == self.led_count)


class TagButton(QToolButton):
    def __init__(self, tagType, manager=None):
        super().__init__()
        self.manager = manager
        self.tagType = tagType
        self.setFixedSize(200, 80)
        self.mainLayout = QVBoxLayout(self)

        self.initButton()

    def initButton(self):
        container = QWidget()
        containerLayout = QHBoxLayout(container)
        self.setFixedSize(100, 100)

        self.color = QLabel()
        self.color.setFixedSize(10, 10)
        self.color.setStyleSheet(
            f"background-color: rgb({self.tagType.color});border-radius: 5px;"
        )

        self.name = QLabel(self.tagType.name)
        self.pin = QLabel(f"seg:{self.tagType.pin}")

        containerLayout.addWidget(self.color)
        containerLayout.addWidget(self.name)
        containerLayout.addWidget(self.pin)

        self.mainLayout.addWidget(container)

    def contextMenuEvent(self, a0):
        menu = QMenu(self)

        renameAction = QAction("Edit", self)
        renameAction.triggered.connect(self.showEditDialog)
        menu.addAction(renameAction)

        deleteAction = QAction("Delete", self)
        deleteAction.triggered.connect(self.showDeleteDialog)
        menu.addAction(deleteAction)

        menu.exec(a0.globalPos())

    def showEditDialog(self):
        dialog = editDialog(tagType=self.tagType)
        dialog.editType.connect(self.editType)
        dialog.exec()

    def editType(self, params):
        # Rename (name change) has no state equivalent (update_tag_type
        # does not touch name); keep the pre-existing direct mutation.
        # Dict key in manager.types becomes stale -- pre-existing bug,
        # addressed separately.
        self.tagType.name = params["name"]
        state = getattr(self.manager, "_state", None)
        project_window = getattr(self.manager, "_project_window", None)
        commands = getattr(self.manager, "_commands", None)
        if (
            state is not None
            and project_window is not None
            and not project_window.is_loading()
            and self.manager._master_id is not None
            and self.manager._slave_id is not None
        ):
            try:
                if commands is not None:
                    commands.push(
                        EditRangeCommand(
                            master_id=self.manager._master_id,
                            slave_id=self.manager._slave_id,
                            type_name=self.tagType.name,
                            new_pin=str(params["pin"]),
                            new_color=params["color"],
                        )
                    )
                else:
                    state.update_tag_type(
                        self.manager._master_id,
                        self.manager._slave_id,
                        self.tagType.name,
                        pin=str(params["pin"]),
                        color=params["color"],
                    )
                return
            except KeyError:
                import logging

                logging.getLogger(__name__).warning(
                    "state missing tag_type %s during edit",
                    self.tagType.name,
                )
        # Headless / no-state fallback: mutate widget + scene directly.
        self.tagType.color = params["color"]
        self.tagType.pin = params["pin"]
        self.editButton()
        r, g, b = map(int, self.tagType.color.split(","))
        wave = self.manager.box.wave if self.manager.box is not None else None
        controller = getattr(wave, "_tagController", None)
        if controller is not None:
            for tag in controller.scene_tags_for(self.tagType.name):
                tag.setPen(pg.mkPen(QColor(r, g, b), width=1))

    def editButton(self):
        self.color.setStyleSheet(
            f"background-color: rgb({self.tagType.color});border-radius: 5px;"
        )

        self.name = QLabel(self.tagType.name)
        self.pin = QLabel(f"seg:{self.tagType.pin}")

    def showDeleteDialog(self):
        dialog = DeleteDialog(self)
        dialog.boxDelete.connect(self.deleteType)
        dialog.exec()

    def deleteType(self):
        state = getattr(self.manager, "_state", None)
        project_window = getattr(self.manager, "_project_window", None)
        commands = getattr(self.manager, "_commands", None)
        # State-first delete: mutating state fires TagTypeRemoved and the
        # manager's listener tears down scene tags, TagButton, chooseBox
        # entry, and TagState chip. If no state is wired, fall back to
        # the legacy direct cleanup.
        if (
            state is not None
            and project_window is not None
            and not project_window.is_loading()
            and self.manager._master_id is not None
            and self.manager._slave_id is not None
        ):
            try:
                if commands is not None:
                    commands.push(
                        DeleteTagTypeCommand(
                            master_id=self.manager._master_id,
                            slave_id=self.manager._slave_id,
                            type_name=self.tagType.name,
                        )
                    )
                else:
                    state.remove_tag_type(
                        self.manager._master_id,
                        self.manager._slave_id,
                        self.tagType.name,
                    )
                return
            except KeyError:
                import logging

                logging.getLogger(__name__).warning(
                    "state missing tag_type %s during delete",
                    self.tagType.name,
                )
        wave = self.manager.box.wave if self.manager.box is not None else None
        controller = getattr(wave, "_tagController", None)
        if controller is not None:
            controller.remove_scene_tag_type(self.tagType.name)
        self.manager.types.pop(self.tagType.name, None)
        if self.manager.box is not None:
            states = self.manager.box.tagsLayout
            for i in range(states.count()):
                st = states.itemAt(i).widget()
                if st is not None and st.tagType.name == self.tagType.name:
                    st.deleteLater()
        self.deleteLater()
