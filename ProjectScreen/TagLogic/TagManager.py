import logging

import pyqtgraph as pg
from PyQt6.QtCore import QEvent, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QApplication,
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
from lightconductor.application.grid_sizing import compute_cell_size
from lightconductor.application.grid_zoom import (
    DEFAULT_MIN_CELL,
    apply_wheel_zoom,
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
    # Emitted when ``curType`` changes — either via the user picking a
    # different TagButton (``setNewType``) or because the current type
    # was removed (``_handle_tag_type_removed``). Payload is the new
    # ``curType`` (a widget-side ``TagType`` or ``None``). Consumed by
    # the popout Tag editor window so it can rebind its preview /
    # colors to whatever type the active slave is now pointed at.
    currentTypeChanged = pyqtSignal(object)

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
        grid_rows = int(getattr(self.box, "_grid_rows", 1) or 1) if self.box else 1
        grid_columns = (
            int(getattr(self.box, "_grid_columns", 0) or 0) if self.box else 0
        )
        led_cells_raw = getattr(self.box, "_led_cells", None) if self.box else None
        led_cells = frozenset(int(c) for c in led_cells_raw) if led_cells_raw else None
        occupied_cells: set[int] = set()
        for tag_type in self.types.values():
            for cell in getattr(tag_type, "topology", None) or []:
                try:
                    occupied_cells.add(int(cell))
                except (TypeError, ValueError):
                    continue
        dialog = newTypeDialog(
            self,
            led_count=led_count,
            occupied_ranges=self.getOccupiedRanges(),
            slave_grid_rows=grid_rows,
            slave_grid_columns=grid_columns,
            occupied_cells=occupied_cells,
            led_cells=led_cells,
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
            self.currentTypeChanged.emit(None)

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
        self.currentTypeChanged.emit(self.curType)


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

    def __init__(
        self,
        parent=None,
        led_count=0,
        occupied_ranges=None,
        slave_grid_rows=1,
        slave_grid_columns=0,
        occupied_cells=None,
        led_cells=None,
    ):
        super().__init__(parent=parent)
        self.setWindowTitle("New range")
        self.led_count = led_count
        self.occupied_ranges = occupied_ranges or []
        self._slave_grid_rows = max(1, int(slave_grid_rows or 1))
        self._slave_grid_columns = max(0, int(slave_grid_columns or 0))
        self._occupied_cells = (
            frozenset(occupied_cells) if occupied_cells else frozenset()
        )
        self._led_cells = frozenset(led_cells) if led_cells is not None else None
        self.mainLayout = QVBoxLayout(self)
        self.initParams()

    def initParams(self):
        self.newNameBar = self.LabelAndLine("Name")

        self.colorPicker = ColorPicker()
        self.layout().addWidget(self.colorPicker)

        self.rangeLengthBar = self.LabelAndLine("Range length")
        self.rangeLengthBar.setText("1")

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
        if length <= 0:
            length = 1
        start = self.rangeStartCombo.currentText() or "0"
        topology = self.topology
        if topology is None or len(topology) != length:
            topology = [i for i in range(length)]
        params = {
            "name": self.newNameBar.text(),
            "color": f"{self.colorPicker.rgb[0]}, {self.colorPicker.rgb[1]}, {self.colorPicker.rgb[2]}",  # noqa: E501
            "pin": start,
            "row": 1,
            "table": len(topology),
            "topology": topology,
        }
        self.newType.emit(params)
        self.accept()

    def configureTopology(self):
        try:
            length = int(self.rangeLengthBar.text())
        except ValueError:
            length = 1
        dialog = TopologyDialog(
            slave_grid_rows=self._slave_grid_rows,
            slave_grid_columns=self._slave_grid_columns,
            max_selection=max(1, length),
            occupied_cells=self._occupied_cells,
            led_cells=self._led_cells,
            order=self.topology,
            parent=self,
        )
        if dialog.exec():
            self.topology = dialog.order


class TopologyDialog(QDialog):
    """Pick which slave-grid cells belong to this range.

    Mouse wheel over the grid zooms cells in/out. The first wheel
    tick pins the cell size to a manual value; subsequent dialog
    resizes no longer re-fit (``_user_zoomed``). A ``QScrollArea``
    wraps the grid so oversized content scrolls. The counter label
    and OK button stay outside the scroll area so wheeling over them
    keeps its normal behavior.
    """

    def __init__(
        self,
        slave_grid_rows,
        slave_grid_columns,
        max_selection,
        occupied_cells=None,
        led_cells=None,
        order=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Range topology")
        self.rows = max(1, int(slave_grid_rows or 1))
        self.cols = max(1, int(slave_grid_columns or 1))
        self.max_selection = max(0, int(max_selection or 0))
        self.occupied = frozenset(occupied_cells) if occupied_cells else frozenset()
        self.led_cells = frozenset(led_cells) if led_cells is not None else None
        self.order = list(order) if order else []
        self.order = [
            c
            for c in self.order
            if 0 <= c < self.rows * self.cols
            and c not in self.occupied
            and (self.led_cells is None or c in self.led_cells)
        ]
        if len(self.order) > self.max_selection:
            self.order = self.order[: self.max_selection]
        self.buttons = {}

        # Drag-paint state: mode is "ADD", "REMOVE", or None. Visited
        # cells are deduped per-drag so revisiting a cell doesn't
        # double-toggle it.
        self._drag_active: bool = False
        self._drag_mode: str | None = None
        self._drag_visited: set[int] = set()
        # Set when a drag's press cell is applied via the event-filter
        # pipeline. The subsequent Qt `clicked` signal on the press
        # cell would otherwise re-invoke toggleCell and undo the drag,
        # so toggleCell consumes and clears this flag.
        self._suppress_next_click: bool = False

        # Zoom state. ``_cell_size`` is the pixel side of each square
        # cell button. ``_user_zoomed`` flips True on the first wheel
        # tick; while True, resizeEvent stops re-fitting and the
        # user's manual size sticks.
        self._cell_size: int = 32
        self._user_zoomed: bool = False

        # Middle-button pan state. Active only while the middle
        # button is held. Orthogonal to left-button drag-paint.
        self._pan_active: bool = False
        self._pan_start_global: QPoint | None = None
        self._pan_scroll_start: tuple[int, int] = (0, 0)

        layout = QVBoxLayout(self)
        self.counterLabel = QLabel("")
        layout.addWidget(self.counterLabel)
        self._gridWidget = QWidget()
        gridLayout = QVBoxLayout(self._gridWidget)
        gridLayout.setContentsMargins(0, 0, 0, 0)
        gridLayout.setSpacing(0)
        for r in range(self.rows):
            rowWidget = QWidget()
            rowLayout = QHBoxLayout(rowWidget)
            rowLayout.setContentsMargins(0, 0, 0, 0)
            rowLayout.setSpacing(0)
            for c in range(self.cols):
                index = r * self.cols + c
                btn = QPushButton("")
                btn.setCheckable(True)
                has_no_led = self.led_cells is not None and index not in self.led_cells
                if index in self.occupied:
                    btn.setEnabled(False)
                    btn.setText("·")
                    btn.setStyleSheet(
                        "QPushButton { background-color: #4a2020; color: #888;}"
                    )
                elif has_no_led:
                    btn.setEnabled(False)
                    btn.setText("—")
                    btn.setStyleSheet(
                        "QPushButton { background-color: #ffffff; color: #333333;}"
                    )
                else:
                    btn.clicked.connect(lambda checked, i=index: self.toggleCell(i))
                    btn.installEventFilter(self)
                self.buttons[index] = btn
                rowLayout.addWidget(btn)
            gridLayout.addWidget(rowWidget)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(False)
        self._scroll.setWidget(self._gridWidget)
        self._scroll.viewport().installEventFilter(self)
        layout.addWidget(self._scroll)

        okBtn = QPushButton("OK")
        okBtn.clicked.connect(self.accept)
        self.okBtn = okBtn
        layout.addWidget(okBtn)

        self.syncButtons()
        # Reasonable initial dialog size; resizeEvent recomputes cells.
        initial_side = 32
        initial_w = max(240, self.cols * initial_side + 40)
        initial_h = max(180, self.rows * initial_side + 120)
        self.resize(initial_w, initial_h)
        self._fit_cell_size()
        self._apply_cell_size()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._user_zoomed:
            self._fit_cell_size()
        self._apply_cell_size()

    def _fit_cell_size(self) -> None:
        viewport = self._scroll.viewport()
        w = viewport.width()
        h = viewport.height()
        self._cell_size = compute_cell_size(
            w,
            h,
            self.rows,
            self.cols,
            min_size=DEFAULT_MIN_CELL,
        )

    def _apply_cell_size(self):
        if not self.buttons:
            return
        side = self._cell_size
        for btn in self.buttons.values():
            btn.setFixedSize(side, side)
        self._gridWidget.setFixedSize(
            self.cols * side,
            self.rows * side,
        )

    def _on_wheel_zoom(self, delta: int) -> None:
        if delta == 0:
            return
        self._user_zoomed = True
        self._cell_size = apply_wheel_zoom(self._cell_size, delta)
        self._apply_cell_size()

    def toggleCell(self, index):
        if self._suppress_next_click:
            self._suppress_next_click = False
            return
        if index in self.occupied:
            return
        if self.led_cells is not None and index not in self.led_cells:
            return
        if index in self.order:
            self.order.remove(index)
        else:
            if len(self.order) >= self.max_selection:
                return
            self.order.append(index)
        self.syncButtons()

    # --- Drag-paint -----------------------------------------------------

    def _cell_eligible(self, index: int) -> bool:
        if index in self.occupied:
            return False
        if self.led_cells is not None and index not in self.led_cells:
            return False
        return True

    def _drag_begin(self, index: int) -> None:
        """Start a drag. Mode is ADD if press cell is free, REMOVE if
        press cell is already in the topology, NONE for disabled cells."""
        if not self._cell_eligible(index):
            self._drag_active = False
            self._drag_mode = None
            self._drag_visited = set()
            return
        self._drag_active = True
        self._drag_mode = "REMOVE" if index in self.order else "ADD"
        self._drag_visited = set()
        self._suppress_next_click = True
        self._drag_apply(index)

    def _drag_apply(self, index: int) -> None:
        if not self._drag_active or self._drag_mode is None:
            return
        if index in self._drag_visited:
            return
        self._drag_visited.add(index)
        if not self._cell_eligible(index):
            return
        if self._drag_mode == "ADD":
            if index in self.order:
                return
            if len(self.order) >= self.max_selection:
                return
            self.order.append(index)
        else:  # REMOVE
            if index not in self.order:
                return
            self.order.remove(index)
        self.syncButtons()

    def _drag_end(self) -> None:
        self._drag_active = False
        self._drag_mode = None
        self._drag_visited = set()

    def _index_at_global(self, global_pos) -> int | None:
        """Return the cell index under the given global screen pos,
        or None if the position is not over any live button."""
        w = QApplication.widgetAt(global_pos)
        for idx, btn in self.buttons.items():
            if btn is w:
                return idx
        return None

    def eventFilter(self, obj, event):  # type: ignore[override]
        et = event.type()
        if et == QEvent.Type.Wheel and obj is self._scroll.viewport():
            if isinstance(event, QWheelEvent):
                delta = event.angleDelta().y()
                if delta != 0:
                    self._on_wheel_zoom(delta)
                    event.accept()
                    return True
            return False
        if (
            et == QEvent.Type.MouseButtonPress
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.MiddleButton
        ):
            self._pan_begin(event.globalPosition().toPoint())
            return True
        if (
            et == QEvent.Type.MouseMove
            and isinstance(event, QMouseEvent)
            and self._pan_active
        ):
            self._pan_apply(event.globalPosition().toPoint())
            return True
        if (
            et == QEvent.Type.MouseButtonRelease
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.MiddleButton
            and self._pan_active
        ):
            self._pan_end()
            return True
        if (
            et == QEvent.Type.MouseButtonPress
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.LeftButton
        ):
            for idx, btn in self.buttons.items():
                if btn is obj:
                    self._drag_begin(idx)
                    return False
        elif (
            et == QEvent.Type.MouseMove
            and isinstance(event, QMouseEvent)
            and self._drag_active
        ):
            idx = self._index_at_global(event.globalPosition().toPoint())
            if idx is not None:
                self._drag_apply(idx)
            return False
        elif (
            et == QEvent.Type.MouseButtonRelease
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.LeftButton
            and self._drag_active
        ):
            self._drag_end()
            return False
        return super().eventFilter(obj, event)

    # --- Middle-button pan ---------------------------------------------

    def _pan_begin(self, global_pos: QPoint) -> None:
        self._pan_active = True
        self._pan_start_global = global_pos
        hbar = self._scroll.horizontalScrollBar()
        vbar = self._scroll.verticalScrollBar()
        self._pan_scroll_start = (hbar.value(), vbar.value())
        self._scroll.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def _pan_apply(self, global_pos: QPoint) -> None:
        if self._pan_start_global is None:
            return
        delta = global_pos - self._pan_start_global
        h0, v0 = self._pan_scroll_start
        self._scroll.horizontalScrollBar().setValue(h0 - delta.x())
        self._scroll.verticalScrollBar().setValue(v0 - delta.y())

    def _pan_end(self) -> None:
        self._pan_active = False
        self._pan_start_global = None
        self._scroll.viewport().unsetCursor()

    def syncButtons(self):
        for index, btn in self.buttons.items():
            if index in self.occupied:
                continue
            if self.led_cells is not None and index not in self.led_cells:
                continue
            if index in self.order:
                position = self.order.index(index)
                btn.setChecked(True)
                btn.setText(str(position))
            else:
                btn.setChecked(False)
                btn.setText("")
        self.counterLabel.setText(
            f"Selected LEDs: {len(self.order)}/{self.max_selection}"
        )
        self.okBtn.setEnabled(len(self.order) == self.max_selection)


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
