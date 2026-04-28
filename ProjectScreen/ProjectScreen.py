import logging
from datetime import datetime

from PyQt6.QtCore import QEvent, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from AssistanceTools.SimpleDialog import SimpleDialog
from lightconductor.application.beat_detection import snap_to_nearest_beat
from lightconductor.application.commands import (
    AddMasterCommand,
    CommandStack,
    CompositeCommand,
    DeleteTagCommand,
)
from lightconductor.application.compiled_show import CompileShowsForMastersUseCase
from lightconductor.application.project_search import compute_visibility
from lightconductor.application.project_state import (
    MasterUpdated,
    ProjectState,
    SlaveUpdated,
    StateReplaced,
)
from lightconductor.application.score_export import (
    build_score_records,
    render_csv,
    render_json,
)
from lightconductor.application.upload_plan import (
    UploadPlan,
    build_upload_plan,
)
from lightconductor.application.validation_service import (
    SEVERITY_ERROR,
    ValidationIssue,
    ValidationService,
)
from lightconductor.config import load_settings, save_settings
from lightconductor.domain.models import Master as DomainMaster
from lightconductor.infrastructure.audio_loader import LibrosaAudioLoader
from lightconductor.infrastructure.master_udp_upload_transport import (
    MasterUdpUploadTransport,
    UploadCancelledError,
    UploadFailedError,
)
from lightconductor.infrastructure.project_session_storage import ProjectSessionStorage
from lightconductor.infrastructure.ui_session_bridge import UiSessionBridge
from lightconductor.presentation.project_controller import ProjectScreenController
from lightconductor.presentation.project_session_controller import (
    ProjectSessionController,
)
from ProjectScreen.PlateLogic.LedPreviewWindow import LedPreviewWindow
from ProjectScreen.PlateLogic.MasterBox import MasterBox
from ProjectScreen.PlateLogic.TagPinsDialog import TagPinsDialog
from ProjectScreen.TagLogic.TagClipboard import (
    build_cut_commands,
    build_paste_command,
    make_clipboard_from_selection,
)
from ProjectScreen.TagLogic.TagFlip import build_flip_commands
from ProjectScreen.TagLogic.TagTimelineController import SNAP_GRANULARITY_SECONDS
from ProjectScreen.upload_preview_dialog import (
    MasterPreviewRow,
    UploadPreviewDialog,
)

logger = logging.getLogger(__name__)


# Диалог создания нового мастера
class newMasterDialog(SimpleDialog):
    masterCreated = pyqtSignal(dict)

    def __init__(self, default_ip: str, parent=None):
        super().__init__(parent)
        self._default_ip = default_ip
        self.uiCreate()

    def uiCreate(self):
        self.mainLayout = QVBoxLayout(self)

        self.masterNameBar = self.LabelAndLine("Master's name")
        self.masterIpBar = self.LabelAndLine("Master IP")
        self.masterIpBar.setText(self._default_ip)
        okButton = self.OkAndCancel()
        okButton.clicked.connect(self.onOkClicked)

    def onOkClicked(self):
        data = {
            "name": self.masterNameBar.text(),
            "ip": self.masterIpBar.text(),
        }
        self.masterCreated.emit(data)
        self.accept()


class ProjectWindow(QMainWindow):
    # Emitted whenever ``set_active_slave`` is called. Subscribers
    # (currently LedPreviewWindow) use this to re-wire their views
    # to the newly-active slave without needing per-slave signal
    # connections on the project window itself.
    activeSlaveChanged = pyqtSignal(object)

    def __init__(self, project_data):
        super().__init__()
        self.settings = load_settings()
        self.masters = {}
        self.project_data = project_data
        self.audio = None
        self.sr = None
        self.boxCounter = 0
        self.boxes = {}
        self.audioPath = None
        self._project_storage = ProjectSessionStorage()
        self._project_name = self.project_data["project_name"]
        self._audio_offset_ms: int = self._project_storage.load_audio_offset_ms(
            self._project_name,
        )
        self.sessionController = ProjectSessionController(
            UiSessionBridge(
                domain_storage=self._project_storage,
                project_name=self._project_name,
            )
        )
        self.showController = ProjectScreenController(
            compile_use_case=CompileShowsForMastersUseCase(),
            transport=MasterUdpUploadTransport(
                port=self.settings.udp_port,
                chunk_size=self.settings.udp_chunk_size,
                chunk_redundancy=self.settings.udp_chunk_redundancy,
            ),
            audio_loader=LibrosaAudioLoader(),
        )
        self.validation_service = ValidationService()
        self.state = ProjectState()
        self.commands = CommandStack(self.state)
        self._loading = False

        self._dirty: bool = False
        self._base_window_title: str = ""
        self._active_slave = None
        self._tag_clipboard = None
        self._preview_window: LedPreviewWindow | None = None
        self._tag_pins_window: TagPinsDialog | None = None
        self._tag_edit_windows: list[TagPinsDialog] = []
        self._unsubscribe_dirty = self.state.subscribe(
            self._on_state_event_dirty,
        )
        # Re-apply search filter on state mutations so newly-added
        # entities respect the active filter. singleShot(0) defers to
        # the next event-loop tick, letting widget-side bridges finish
        # building the new subtree before we query visibility.
        self._search_unsubscribe = self.state.subscribe(
            self._on_state_event_search,
        )
        self._master_updated_unsubscribe = self.state.subscribe(
            self._on_state_event_master_updated,
        )
        self._slave_updated_unsubscribe = self.state.subscribe(
            self._on_state_event_slave_updated,
        )
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(
            max(1, int(self.settings.autosave_interval_seconds)) * 1000,
        )
        self._autosave_timer.timeout.connect(self._autosave_tick)
        self._autosave_timer.start()

        self.initActions()
        self.init_ui()
        self.initExistingData()
        self.initAudioPlayer()

    def is_loading(self) -> bool:
        return self._loading

    # создание действий под горячие клавиши
    def initActions(self):
        saveAction = QAction("Save", self)
        saveAction.setShortcut(QKeySequence("Ctrl+S"))
        saveAction.triggered.connect(self.saveData)
        self.addAction(saveAction)

        undoAction = QAction("Undo", self)
        undoAction.setShortcut(QKeySequence("Ctrl+Z"))
        undoAction.triggered.connect(self.commands.undo)
        self.addAction(undoAction)

        redoAction = QAction("Redo", self)
        redoAction.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        redoAction.triggered.connect(self.commands.redo)
        self.addAction(redoAction)

        spaceAction = QAction("Play/Pause", self)
        spaceAction.setShortcut(QKeySequence(Qt.Key.Key_Space))
        spaceAction.triggered.connect(self._on_space)
        self.addAction(spaceAction)

        addTagAction = QAction("Add tag at cursor", self)
        addTagAction.setShortcut(QKeySequence("Ctrl+T"))
        addTagAction.triggered.connect(self._on_add_tag_at_cursor)
        self.addAction(addTagAction)

        addTagBeatAction = QAction("Add tag at cursor (beat snap)", self)
        addTagBeatAction.setShortcut(QKeySequence("Ctrl+Shift+T"))
        addTagBeatAction.triggered.connect(self._on_add_tag_at_cursor_beat)
        self.addAction(addTagBeatAction)

        deleteTagAction = QAction("Delete selected tag", self)
        deleteTagAction.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        deleteTagAction.triggered.connect(self._on_delete_selected_tag)
        self.addAction(deleteTagAction)

        copyTagAction = QAction("Copy tag", self)
        copyTagAction.setShortcut(QKeySequence("Ctrl+C"))
        copyTagAction.triggered.connect(self._on_copy_tag)
        self.addAction(copyTagAction)

        pasteTagAction = QAction("Paste tag", self)
        pasteTagAction.setShortcut(QKeySequence("Ctrl+V"))
        pasteTagAction.triggered.connect(self._on_paste_tag)
        self.addAction(pasteTagAction)

        cutTagAction = QAction("Cut tag", self)
        cutTagAction.setShortcut(QKeySequence("Ctrl+X"))
        cutTagAction.triggered.connect(self._on_cut_tag)
        self.addAction(cutTagAction)

        flipHAction = QAction("Flip selected tags horizontally", self)
        flipHAction.setShortcut(QKeySequence("H"))
        flipHAction.triggered.connect(self._on_flip_selected_horizontal)
        self.addAction(flipHAction)

        flipVAction = QAction("Flip selected tags vertically", self)
        flipVAction.setShortcut(QKeySequence("V"))
        flipVAction.triggered.connect(self._on_flip_selected_vertical)
        self.addAction(flipVAction)

    def set_active_slave(self, slave):
        # Idempotent: SlaveBox.wave emits waveActivated on any wave
        # interaction (including playhead moves), so this method can be
        # called repeatedly with the same slave. Emitting on every call
        # caused subscribers (TagPinsDialog) to rebuild their grids and
        # wipe in-progress edits.
        if slave is self._active_slave:
            return
        self._active_slave = slave
        self.activeSlaveChanged.emit(slave)

    def showLedPreviewWindow(self):
        """Open the popout LED preview, or raise/focus it if already
        open. One instance per project window; closing destroys it
        (WA_DeleteOnClose) and clears the reference via the
        ``destroyed`` signal."""
        if self._preview_window is not None:
            self._preview_window.raise_()
            self._preview_window.activateWindow()
            return
        window = LedPreviewWindow(self, parent=self)
        self._preview_window = window
        window.destroyed.connect(self._on_preview_window_destroyed)
        window.show()

    def _on_preview_window_destroyed(self, _obj=None):
        self._preview_window = None

    def showTagEditorWindow(self):
        """Open the singleton Tag editor window, or raise/focus it if
        already open. Mirrors ``showLedPreviewWindow``: the window is
        ``WA_DeleteOnClose`` and its ``destroyed`` signal clears the
        reference here so the next click rebuilds fresh."""
        if self._tag_pins_window is not None:
            self._tag_pins_window.raise_()
            self._tag_pins_window.activateWindow()
            return
        window = TagPinsDialog(project_window=self, parent=self)
        self._tag_pins_window = window
        window.destroyed.connect(self._on_tag_pins_window_destroyed)
        window.show()

    def _on_tag_pins_window_destroyed(self, _obj=None):
        self._tag_pins_window = None

    def openTagEditWindow(self, scene_tag):
        """Open a fresh edit-mode :class:`TagPinsDialog` bound to the
        given scene tag. Multiple simultaneous edit windows are
        supported — each is tracked in ``self._tag_edit_windows`` and
        removed from the list when the underlying widget is destroyed
        (``WA_DeleteOnClose``)."""
        manager = getattr(scene_tag, "manager", None)
        if manager is None:
            return
        widget_type = getattr(scene_tag, "type", None)
        if widget_type is None:
            return
        type_name = getattr(widget_type, "name", None)
        if type_name is None:
            return
        master_id = getattr(widget_type, "master_id", None) or getattr(
            manager, "_master_id", None
        )
        slave_id = getattr(widget_type, "slave_id", None) or getattr(
            manager, "_slave_id", None
        )
        if master_id is None or slave_id is None:
            return
        box = getattr(manager, "box", None)
        wave = getattr(box, "wave", None) if box is not None else None
        controller = getattr(wave, "_tagController", None)
        if controller is None:
            return
        domain_id = controller._find_domain_id_for_scene_tag(scene_tag)
        domain_tags = controller._domain_tag_list(type_name)
        if domain_id is None or domain_tags is None:
            return
        domain_tag = None
        for dt in domain_tags:
            if id(dt) == domain_id:
                domain_tag = dt
                break
        if domain_tag is None:
            return
        slave_cols = int(getattr(box, "_grid_columns", 0) or 0) if box else 0
        if slave_cols < 1:
            slave_cols = max(1, int(getattr(widget_type, "table", 1) or 1))
        led_cells = list(getattr(box, "_led_cells", None) or []) if box else []
        window = TagPinsDialog(
            project_window=self,
            parent=self,
            mode="edit",
            tag=domain_tag,
            master_id=str(master_id),
            slave_id=str(slave_id),
            type_name=str(type_name),
            topology=list(getattr(widget_type, "topology", []) or []),
            slave_grid_columns=slave_cols,
            led_cells=led_cells,
        )
        self._tag_edit_windows.append(window)
        window.destroyed.connect(
            lambda _obj=None, w=window: self._on_tag_edit_window_destroyed(w)
        )
        window.show()

    def _on_tag_edit_window_destroyed(self, window):
        try:
            self._tag_edit_windows.remove(window)
        except ValueError:
            pass

    def _focus_in_text_input(self) -> bool:
        fw = QApplication.focusWidget()
        if fw is None:
            return False
        if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
            return True
        if isinstance(fw, QComboBox) and fw.isEditable():
            return True
        return False

    def _on_space(self):
        if self._focus_in_text_input():
            return
        slave = self._active_slave
        if slave is None:
            return
        slave.playButton.click()

    def _on_add_tag_at_cursor(self):
        self._add_tag_at_cursor_impl(beat_snap=False)

    def _on_add_tag_at_cursor_beat(self):
        self._add_tag_at_cursor_impl(beat_snap=True)

    def _add_tag_at_cursor_impl(self, beat_snap: bool):
        if self._focus_in_text_input():
            return
        slave = self._active_slave
        if slave is None:
            return
        wave = slave.wave
        cur_type = wave.manager.curType
        if cur_type is None:
            return
        raw_time = max(0.0, float(wave._renderer.selectedLine.value()))
        beats = getattr(wave._renderer, "beat_times", None) if beat_snap else None
        time_val = snap_to_nearest_beat(raw_time, beats, SNAP_GRANULARITY_SECONDS)
        dur = float(getattr(wave._renderer, "duration", 0.0) or 0.0)
        if dur > 0.0 and time_val > dur:
            time_val = dur
        topology = list(
            getattr(
                cur_type,
                "topology",
                [i for i in range(cur_type.row * cur_type.table)],
            )
        )
        colors = [[0, 0, 0] for _ in range(len(topology))]
        wave.addTagAtTime({"action": False, "colors": colors}, time_val)

    def _on_delete_selected_tag(self):
        if self._focus_in_text_input():
            return
        slave = self._active_slave
        if slave is None:
            return
        wave = slave.wave
        controller = getattr(wave, "_tagController", None)
        selected = (
            list(controller.selected_scene_tags()) if controller is not None else []
        )
        if not selected:
            return
        master_id = controller._master_id
        slave_id = controller._slave_id
        by_type = {}
        for scene_tag in selected:
            type_ = getattr(scene_tag, "type", None)
            type_name = type_.name if type_ is not None else None
            if type_name is None:
                continue
            domain_tags = controller._domain_tag_list(type_name)
            if domain_tags is None:
                continue
            domain_id = controller._find_domain_id_for_scene_tag(scene_tag)
            if domain_id is None:
                continue
            idx = None
            for i, dt in enumerate(domain_tags):
                if id(dt) == domain_id:
                    idx = i
                    break
            if idx is None:
                continue
            by_type.setdefault(type_name, []).append(idx)
        children = []
        for type_name in sorted(by_type.keys()):
            for idx in sorted(by_type[type_name], reverse=True):
                children.append(
                    DeleteTagCommand(
                        master_id=master_id,
                        slave_id=slave_id,
                        type_name=type_name,
                        tag_index=idx,
                    )
                )
        if not children:
            return
        # Pre-clear selection — the TagRemoved listener on the
        # controller will remove scene tags and drop them from
        # the selection set too, but doing this upfront is a
        # belt-and-suspenders safety net against dangling
        # visuals during the composite's execute.
        controller.clear_selection()
        self.commands.push(CompositeCommand(children=children))

    def _on_copy_tag(self):
        if self._focus_in_text_input():
            return
        slave = self._active_slave
        if slave is None:
            return
        controller = getattr(slave.wave, "_tagController", None)
        if controller is None:
            return
        selected = list(controller.selected_scene_tags())
        if not selected:
            return
        clipboard = make_clipboard_from_selection(selected)
        if clipboard is None:
            return
        self._tag_clipboard = clipboard

    def _on_cut_tag(self):
        if self._focus_in_text_input():
            return
        slave = self._active_slave
        if slave is None:
            return
        controller = getattr(slave.wave, "_tagController", None)
        if controller is None:
            return
        selected = list(controller.selected_scene_tags())
        if not selected:
            return
        master_id = getattr(slave, "_master_id", None)
        slave_id = getattr(slave, "boxID", None)
        if master_id is None or slave_id is None:
            return
        try:
            clipboard, composite = build_cut_commands(
                selected_scene_tags=selected,
                controller=controller,
                master_id=master_id,
                slave_id=slave_id,
            )
            if clipboard is None or composite is None:
                return
            self._tag_clipboard = clipboard
            self.commands.push(composite)
            controller.clear_selection()
        except Exception as exc:  # noqa: BLE001 — surface to user
            logger.exception("Cut failed")
            QMessageBox.warning(self, "Cut failed", str(exc))

    def _on_paste_tag(self):
        if self._focus_in_text_input():
            return
        clipboard = self._tag_clipboard
        if clipboard is None or not clipboard.entries:
            return
        slave = self._active_slave
        if slave is None:
            return
        wave = slave.wave
        manager = wave.manager
        master_id = getattr(slave, "_master_id", None)
        slave_id = getattr(slave, "boxID", None)
        if master_id is None or slave_id is None:
            return
        try:
            anchor_time = float(wave._renderer.selectedLine.value())
            composite = build_paste_command(
                clipboard=clipboard,
                target_manager=manager,
                master_id=master_id,
                slave_id=slave_id,
                anchor_time=anchor_time,
            )
            if composite is None:
                return
            self.commands.push(composite)
        except Exception as exc:  # noqa: BLE001 — surface to user
            logger.exception("Paste failed")
            QMessageBox.warning(self, "Paste failed", str(exc))

    def _on_flip_selected_horizontal(self):
        self._flip_selected(axis="horizontal")

    def _on_flip_selected_vertical(self):
        self._flip_selected(axis="vertical")

    def _flip_selected(self, *, axis: str) -> None:
        if self._focus_in_text_input():
            return
        slave = self._active_slave
        if slave is None:
            return
        controller = getattr(slave.wave, "_tagController", None)
        if controller is None:
            return
        selected = list(controller.selected_scene_tags())
        if not selected:
            return
        master_id = getattr(slave, "_master_id", None)
        slave_id = getattr(slave, "boxID", None)
        if master_id is None or slave_id is None:
            return
        slave_cols = int(getattr(slave, "_grid_columns", 0) or 0)
        if slave_cols < 1:
            slave_cols = 1
        try:
            command, skipped = build_flip_commands(
                selected_scene_tags=selected,
                controller=controller,
                master_id=str(master_id),
                slave_id=str(slave_id),
                slave_grid_columns=slave_cols,
                axis=axis,
            )
        except Exception as exc:  # noqa: BLE001 — surface to user
            logger.exception("Flip failed")
            QMessageBox.warning(self, "Flip failed", str(exc))
            return
        if skipped:
            logger.info(
                "Flip (%s): skipped %d action-off tag(s)",
                axis,
                skipped,
            )
        if command is None:
            return
        try:
            self.commands.push(command)
        except Exception as exc:  # noqa: BLE001 — surface to user
            logger.exception("Flip push failed")
            QMessageBox.warning(self, "Flip failed", str(exc))

    def _report_validation_errors(
        self,
        issues: list[ValidationIssue],
        operation_name: str,
    ) -> bool:
        """Show a QMessageBox listing validation errors.
        Returns True if operation should proceed, False if blocked.

        Warnings are NOT shown in a blocking dialog — they are
        logged only. Errors block and are displayed.
        """
        errors = [i for i in issues if i.severity == SEVERITY_ERROR]
        warnings_ = [i for i in issues if i.severity != SEVERITY_ERROR]

        for warning in warnings_:
            logger.warning(
                "Validation warning during %s: [%s] %s — %s",
                operation_name,
                warning.category,
                warning.path,
                warning.message,
            )

        if not errors:
            return True

        lines = [
            f"• [{issue.category}] {issue.path}\n  {issue.message}" for issue in errors
        ]
        QMessageBox.warning(
            self,
            f"{operation_name} blocked",
            "Project has validation errors:\n\n" + "\n\n".join(lines),
        )
        return False

    def _format_upload_preview(
        self,
        plan: UploadPlan,
        warnings: list,
    ) -> str:
        """Compose the QMessageBox body text for the upload
        confirmation dialog."""
        lines = []
        lines.append(
            f"About to upload to "
            f"{plan.total_hosts} host(s), "
            f"{plan.total_slaves} slave(s), "
            f"{plan.total_packets} packet(s) total.",
        )
        if plan.total_bytes > 0:
            lines.append(
                f"Total blob size: {plan.total_bytes} bytes.",
            )
        if plan.estimated_seconds > 0.0:
            lines.append(
                f"Estimated duration: "
                f"~{plan.estimated_seconds:.2f}s "
                f"(inter-packet delay only; "
                f"network jitter not modeled).",
            )
        if plan.hosts:
            lines.append("")
            lines.append("Hosts:")
            for host_plan in plan.hosts:
                slave_summaries = (
                    ", ".join(
                        f"slave {s.slave_id} ({s.blob_size}B, {s.chunk_count} chunks)"
                        for s in host_plan.slaves
                    )
                    or "no slaves"
                )
                lines.append(
                    f"  • {host_plan.host}: {slave_summaries}",
                )
        if warnings:
            lines.append("")
            lines.append(
                f"{len(warnings)} validation warning(s):",
            )
            for w in warnings:
                lines.append(
                    f"  • [{w.category}] {w.path} — {w.message}",
                )
        lines.append("")
        lines.append("Proceed with upload?")
        return "\n".join(lines)

    def _format_upload_failed_message(
        self,
        exc: "UploadFailedError",
    ) -> str:
        """Build a human-readable body for the UploadFailedError dialog
        — host, port, attempts, and likely causes.
        """
        lines = []
        lines.append(
            f"Could not reach master at {exc.host}:{exc.port}.",
        )
        lines.append(
            f"Tried {exc.attempts} time(s), last error: {exc.original}",
        )
        lines.append("")
        lines.append("Possible causes:")
        lines.append(
            "  • Master is powered off or disconnected",
        )
        lines.append(
            "  • Wrong IP address in master settings",
        )
        lines.append(
            f"  • Firewall blocks UDP port {exc.port}",
        )
        lines.append(
            "  • Network interface down",
        )
        lines.append("")
        lines.append(
            "Please check the connection and try again.",
        )
        return "\n".join(lines)

    # создание аудио плеера
    def initAudioPlayer(self):
        if self.audio is not None:
            self.audioPlayer = QMediaPlayer()
            self.audioPlayer.setSource(QUrl.fromLocalFile(self.audioPath))
            self.audioOutput = QAudioOutput()
            self.audioPlayer.setAudioOutput(self.audioOutput)

    def init_ui(self):
        self._base_window_title = self.project_data["project_name"]
        self._refresh_window_title()
        self.setGeometry(100, 100, 1400, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel(f"Project: {self.project_data['project_name']}")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.layout.addWidget(title)

        self.initButtons()

    # создание кнопок под юай
    def initButtons(self):
        controls = QWidget()
        controlsLayout = QHBoxLayout(controls)
        controlsLayout.setContentsMargins(0, 0, 0, 0)
        controlsLayout.setSpacing(8)

        addButton = QPushButton("Add track")
        addButton.clicked.connect(self.addTrack)
        controlsLayout.addWidget(addButton)

        waveButton = QPushButton("Add master")
        waveButton.clicked.connect(self.showMasterDialog)
        controlsLayout.addWidget(waveButton)

        uploadButton = QPushButton("Upload show")
        uploadButton.clicked.connect(self.uploadShow)
        controlsLayout.addWidget(uploadButton)

        exportButton = QPushButton("Export score")
        exportButton.clicked.connect(self.exportScore)
        controlsLayout.addWidget(exportButton)

        previewButton = QPushButton("Show LED preview")
        previewButton.clicked.connect(self.showLedPreviewWindow)
        controlsLayout.addWidget(previewButton)

        tagEditorButton = QPushButton("Tag editor")
        tagEditorButton.clicked.connect(self.showTagEditorWindow)
        controlsLayout.addWidget(tagEditorButton)

        showButton = QPushButton("Start show")
        showButton.clicked.connect(self.startShow)
        showButton.setStyleSheet(
            "QPushButton { background-color: #2d6a4f; border: 1px solid #3f8a68; font-weight: 600; }"  # noqa: E501
            "QPushButton:hover { background-color: #347a5a; }"
        )
        controlsLayout.addWidget(showButton)

        audioOffsetLabel = QLabel("Audio offset:")
        controlsLayout.addWidget(audioOffsetLabel)
        self._audio_offset_spin = QSpinBox()
        self._audio_offset_spin.setRange(-2000, 2000)
        self._audio_offset_spin.setSingleStep(10)
        self._audio_offset_spin.setSuffix(" ms")
        self._audio_offset_spin.setValue(self._audio_offset_ms)
        self._audio_offset_spin.setToolTip(
            "Audio offset: positive = audio later than show; "
            "negative = audio earlier. Compensates master start delay."
        )
        self._audio_offset_spin.valueChanged.connect(
            self._on_audio_offset_changed,
        )
        controlsLayout.addWidget(self._audio_offset_spin)

        controlsLayout.addStretch(1)

        self.searchEdit = QLineEdit()
        self.searchEdit.setPlaceholderText("Search masters / slaves / tag types...")
        self.searchEdit.setFixedWidth(240)
        self.searchEdit.textChanged.connect(
            self._on_search_text_changed,
        )
        controlsLayout.addWidget(self.searchEdit)

        self.layout.addWidget(controls)

    def initExistingData(self):
        self._loading = True
        try:
            snapshot = self.sessionController.load_session()
            self.audio = snapshot.audio
            self.sr = snapshot.sample_rate
            self.audioPath = snapshot.audio_path
            self.state.load_masters(snapshot.masters)
            self.commands.clear()
            for master_id, master in snapshot.masters.items():
                self.addMaster(master.name, master_id, master.ip)
                master_widget = self.masters[master_id]
                for slave_id, slave in master.slaves.items():
                    manager = self.initSlave(slave, master_widget, master_id)
                    wave = master_widget.slaves[slave_id].wave
                    for _type_name, tag_type in slave.tag_types.items():
                        self.initTypeAndTags(tag_type, manager, wave)
        finally:
            self._loading = False
        self._set_dirty(False)

    def initSlave(self, slave, master_widget, master_id):
        slaveData = {
            "name": slave.name,
            "pin": slave.pin,
            "led_count": slave.led_count,
            "grid_rows": slave.grid_rows,
            "grid_columns": slave.grid_columns,
            "led_cells": list(slave.led_cells),
        }
        master_widget.addSlave(slaveData, slave.id)
        manager = self.masters[master_id].slaves[slave.id].wave.manager
        return manager

    def initTypeAndTags(self, tag_type, manager, wave):
        params = {
            "name": tag_type.name,
            "color": tag_type.color,
            "pin": tag_type.pin,
            "row": tag_type.rows,
            "table": tag_type.columns,
            "topology": list(tag_type.topology),
        }
        widget_type = manager.addType(params)
        for domain_tag in tag_type.tags:
            tag_dict = {
                "time": domain_tag.time_seconds,
                "action": domain_tag.action,
                "colors": domain_tag.colors,
            }
            wave.addExistingTag(tag_dict, widget_type)

    def update_color_presets(self, presets):
        """Called by TagPinsDialog when the user adds/removes a color
        preset. Mutates self.settings and persists to settings.json.
        Silent on IO errors (logged only).
        """
        self.settings.color_presets = [list(p) for p in (presets or [])]
        try:
            save_settings(self.settings)
        except Exception:
            logger.exception("Failed to save color presets")

    def saveData(self):
        logger.info("Save requested")
        domain_masters = self.state.masters()
        issues = self.validation_service.validate(domain_masters)
        if not self._report_validation_errors(issues, "Save"):
            return
        self.sessionController.save_session(
            self.audio,
            self.sr,
            domain_masters,
        )
        self._set_dirty(False)

    def addTrack(self):
        filePath, _ = QFileDialog.getOpenFileName(
            self,
            "Choose audio",
            "",
            "Аудио файлы (*.mp3, *.wav, *.flac, *.ogg, *.m4a);;Все файлы (*)",
        )
        if not filePath:
            return
        try:
            self.audio, self.sr, self.audioPath = self.showController.load_track(
                filePath
            )
            self.initAudioPlayer()
            self.updateSlavesAudio()
        except FileNotFoundError:
            logger.warning("Audio file not found: %s", filePath)
            QMessageBox.warning(
                self, "Файл не найден", f"Файл не существует:\n{filePath}"
            )
        except Exception as e:
            logger.exception("Failed to load audio track: %s", filePath)
            QMessageBox.critical(self, "Ошибка загрузки трека", str(e))
            return

    def showMasterDialog(self):
        dialog = newMasterDialog(self.settings.default_master_ip, self)
        dialog.masterCreated.connect(self.addMaster)
        dialog.exec()

    def addMaster(self, masterName, boxID=None, masterIp=None):
        if isinstance(masterName, dict):
            masterIp = masterName.get("ip", masterIp)
            masterName = masterName.get("name", "")
        if masterIp is None:
            masterIp = self.settings.default_master_ip
        if boxID is None:
            boxID = datetime.now().strftime("%Y%m%d%H%M%S%f")
        master = MasterBox(
            title=masterName,
            boxID=boxID,
            audio=self.audio,
            sr=self.sr,
            aydioPath=self.audioPath,
            masterIp=masterIp,
            state=self.state,
            project_window=self,
            commands=self.commands,
        )
        self.masters[boxID] = master
        self.layout.addWidget(master)
        if not self._loading:
            self.commands.push(
                AddMasterCommand(
                    master=DomainMaster(
                        id=boxID,
                        name=masterName,
                        ip=masterIp,
                    ),
                )
            )

    def updateSlavesAudio(self):
        for master in self.masters.values():
            master.audio = self.audio
            master.sr = self.sr
            master.audioPath = self.audioPath
            for slave in master.slaves.values():
                slave.wave.setAudioData(self.audio, self.sr, self.audioPath)
                slave.wave.clear()
                slave.wave.init_ui()
                if hasattr(slave, "miniMap") and slave.miniMap is not None:
                    slave.miniMap.setData(
                        audioData=self.audio,
                        sr=self.sr,
                        duration=slave.wave._renderer.duration,
                    )

    def uploadShow(self):
        domain_masters = self.state.masters()
        issues = self.validation_service.validate(domain_masters)
        if not self._report_validation_errors(issues, "Upload"):
            return
        # Separate warnings for the preview dialog
        # (errors already blocked above).
        warnings_only = [i for i in issues if i.severity != SEVERITY_ERROR]
        # Pre-compile for the preview. Compile is pure and cheap;
        # the second compile inside upload_show is intentional and
        # acceptable for MVP.
        try:
            compiled_by_host = self.showController.compile_use_case.execute(
                domain_masters,
            )
        except Exception as exc:
            logger.exception("Compile failed during upload preview")
            QMessageBox.critical(
                self,
                "Upload blocked",
                f"Cannot compile the show:\n{exc}",
            )
            return

        masters_by_id = dict(domain_masters)
        sorted_masters = sorted(
            masters_by_id.values(),
            key=lambda m: m.name or "",
        )
        master_rows = []
        for master in sorted_masters:
            blob_size = sum(
                len(s.blob) for s in compiled_by_host.get(master.ip, [])
            )
            master_rows.append(
                MasterPreviewRow(
                    master_id=master.id,
                    display_name=master.name or master.id,
                    ip=master.ip or "",
                    slaves_count=len(master.slaves),
                    blob_size_bytes=blob_size,
                ),
            )

        def _filtered_compiled(selected_ids):
            selected_hosts = {
                masters_by_id[mid].ip
                for mid in selected_ids
                if mid in masters_by_id
            }
            return {
                host: shows
                for host, shows in compiled_by_host.items()
                if host in selected_hosts
            }

        def _summary(selected_ids):
            filtered = _filtered_compiled(selected_ids)
            sub_plan = build_upload_plan(
                compiled_by_host=filtered,
                chunk_size=self.settings.udp_chunk_size,
                inter_packet_delay=(
                    self.showController.transport.inter_packet_delay
                ),
                chunk_redundancy=self.settings.udp_chunk_redundancy,
            )
            return self._format_upload_preview(sub_plan, warnings_only)

        dialog = UploadPreviewDialog(master_rows, _summary, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            logger.info("Upload cancelled by user at preview dialog")
            return
        selected_ids = dialog.selected_master_ids()

        plan = build_upload_plan(
            compiled_by_host=_filtered_compiled(selected_ids),
            chunk_size=self.settings.udp_chunk_size,
            inter_packet_delay=(self.showController.transport.inter_packet_delay),
            chunk_redundancy=self.settings.udp_chunk_redundancy,
        )

        progress = QProgressDialog(
            "Uploading show: 0 / 0 packets",
            "Cancel",
            0,
            max(1, plan.total_packets),
            self,
        )
        progress.setWindowTitle("Upload in progress")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(True)
        progress.setAutoReset(True)
        progress.setValue(0)

        def _cb(sent: int, total: int) -> bool:
            if progress.wasCanceled():
                return False
            progress.setLabelText(
                f"Uploading show: {sent} / {total} packets",
            )
            progress.setMaximum(max(1, total))
            progress.setValue(sent)
            QApplication.processEvents()
            return True

        try:
            self.showController.upload_show(
                domain_masters,
                selected_master_ids=selected_ids,
                progress_callback=_cb,
            )
            logger.info(
                "Compiled show uploaded (%d hosts, %d slaves, %d packets)",
                plan.total_hosts,
                plan.total_slaves,
                plan.total_packets,
            )
            progress.setValue(max(1, plan.total_packets))
        except UploadCancelledError as exc:
            progress.close()
            logger.info(
                "Upload cancelled by user after %d/%d packets",
                exc.packets_sent,
                exc.total_packets,
            )
            QMessageBox.information(
                self,
                "Upload cancelled",
                f"Sent {exc.packets_sent} of "
                f"{exc.total_packets} packet(s) before cancel.",
            )
        except UploadFailedError as exc:
            progress.close()
            logger.exception(
                "Upload failed: %s",
                exc,
            )
            QMessageBox.critical(
                self,
                "Upload failed",
                self._format_upload_failed_message(exc),
            )
        except Exception as exc:
            progress.close()
            logger.exception("Failed to upload show")
            QMessageBox.critical(
                self,
                "Upload failed",
                f"{exc}",
            )

    def exportScore(self):
        domain_masters = self.state.masters()
        if not domain_masters:
            QMessageBox.information(
                self,
                "Nothing to export",
                "The project has no masters or tags to export.",
            )
            return
        file_path, chosen_filter = QFileDialog.getSaveFileName(
            self,
            "Export score",
            f"{self.project_data.get('project_name', 'score')}.csv",
            "CSV (*.csv);;JSON (*.json)",
        )
        if not file_path:
            return
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        if ext not in ("csv", "json"):
            if "JSON" in (chosen_filter or "").upper():
                ext = "json"
                file_path = file_path + ".json"
            else:
                ext = "csv"
                file_path = file_path + ".csv"
        try:
            records = build_score_records(domain_masters)
            if ext == "csv":
                payload = render_csv(records)
            else:
                payload = render_json(records)
            with open(file_path, "w", encoding="utf-8", newline="") as f:
                f.write(payload)
        except OSError as exc:
            logger.exception("Failed to write score export")
            QMessageBox.critical(
                self,
                "Export failed",
                f"Could not write {file_path}:\n{exc}",
            )
            return
        except Exception as exc:
            logger.exception("Unexpected error during score export")
            QMessageBox.critical(
                self,
                "Export failed",
                f"Unexpected error:\n{exc}",
            )
            return
        logger.info(
            "Exported %d score records to %s",
            len(records),
            file_path,
        )

    def _on_audio_offset_changed(self, value: int) -> None:
        self._audio_offset_ms = int(value)
        try:
            self._project_storage.save_audio_offset_ms(
                self._project_name,
                self._audio_offset_ms,
            )
        except Exception:
            logger.exception("Failed to persist audio offset")
            return
        logger.info("Audio offset set to %d ms", self._audio_offset_ms)

    def startShow(self):
        if not hasattr(self, "audioPlayer"):
            logger.warning("Audio player not initialized, track required")
            QMessageBox.warning(self, "Нет трека", "Сначала добавьте аудио-трек.")
            return

        offset = self._audio_offset_ms
        udp_delay_ms = max(0, offset)
        audio_delay_ms = max(0, -offset)

        def _send_udp():
            try:
                self.showController.send_start_signal(self.state.masters())
                logger.info(
                    "Start signal sent (offset=%dms, "
                    "udp_delay=%dms, audio_delay=%dms)",
                    offset,
                    udp_delay_ms,
                    audio_delay_ms,
                )
            except Exception as e:
                logger.exception("Failed to send start signal")
                QMessageBox.critical(self, "Ошибка старта шоу", str(e))

        def _play_audio():
            self.audioPlayer.setPosition(0)
            self.audioPlayer.play()

        # Both branches are scheduled via singleShot — even with
        # offset==0 they still fire on the next event-loop tick,
        # which keeps the dispatch consistent across all offsets
        # and avoids off-by-tick drift between the two paths.
        QTimer.singleShot(udp_delay_ms, _send_udp)
        QTimer.singleShot(audio_delay_ms, _play_audio)

    def _on_search_text_changed(self, _text: str):
        self._apply_search_filter()

    def _apply_search_filter(self):
        """Walk the current widget tree and apply visibility decisions
        from compute_visibility. Safe to call when self.masters is
        empty or widgets are still being built — missing ids are
        silently skipped."""
        query = ""
        if hasattr(self, "searchEdit") and self.searchEdit is not None:
            query = self.searchEdit.text()
        domain_masters = self.state.masters()
        decisions = compute_visibility(domain_masters, query)
        for master_id, master_widget in self.masters.items():
            mv = decisions.get(master_id)
            if mv is None:
                master_widget.setVisible(True)
                continue
            master_widget.setVisible(mv.visible)
            slaves_widgets = getattr(master_widget, "slaves", {})
            for slave_id, slave_widget in slaves_widgets.items():
                sv = mv.slaves.get(slave_id)
                if sv is None:
                    slave_widget.setVisible(True)
                    continue
                slave_widget.setVisible(sv.visible)
                manager = getattr(
                    getattr(slave_widget, "wave", None),
                    "manager",
                    None,
                )
                if manager is None:
                    continue
                type_widgets = getattr(manager, "types", {}) or {}
                for type_name, widget_type in type_widgets.items():
                    tt_visible = sv.tag_types.get(type_name, True)
                    button = self._find_tag_button(manager, widget_type)
                    if button is not None:
                        button.setVisible(tt_visible)

    def _find_tag_button(self, manager, widget_type):
        """Locate the TagButton in the TagManager whose tagType matches
        widget_type. TagManager stores them in self.buttons
        (QButtonGroup) — iterate and match by the tagType attribute.
        Returns None if not found. Tolerant: the QButtonGroup API may
        not be present in test stubs."""
        buttons_group = getattr(manager, "buttons", None)
        if buttons_group is None:
            return None
        try:
            buttons = buttons_group.buttons()
        except AttributeError:
            return None
        for btn in buttons:
            if getattr(btn, "tagType", None) is widget_type:
                return btn
        return None

    def _on_state_event_search(self, _event):
        if self._loading:
            return
        QTimer.singleShot(0, self._apply_search_filter)

    def _on_state_event_dirty(self, event):
        if self._loading:
            return
        if isinstance(event, StateReplaced):
            return
        self._set_dirty(True)

    def _on_state_event_master_updated(self, event):
        """Route MasterUpdated events to the relevant MasterBox so its
        header label (and ping target) reflect the edited IP. Generic
        're-read master' dispatch — future non-IP fields on Master
        would hook in here too."""
        if not isinstance(event, MasterUpdated):
            return
        box = self.masters.get(event.master_id)
        if box is None:
            return
        try:
            master = self.state.master(event.master_id)
        except KeyError:
            return
        box.setMasterIp(master.ip)

    def _on_state_event_slave_updated(self, event):
        """Route SlaveUpdated events to the relevant SlaveBox. Generic
        're-read slave' dispatch — currently carries brightness edits;
        future non-brightness fields would hook in here too."""
        if not isinstance(event, SlaveUpdated):
            return
        master_box = self.masters.get(event.master_id)
        if master_box is None:
            return
        slave_box = master_box.slaves.get(event.slave_id)
        if slave_box is None:
            return
        try:
            slave = self.state.master(event.master_id).slaves[event.slave_id]
        except KeyError:
            return
        slave_box.setBrightness(slave.brightness)

    def _set_dirty(self, value: bool):
        if self._dirty == value:
            return
        self._dirty = value
        self._refresh_window_title()

    def _refresh_window_title(self):
        title = self._base_window_title
        if self._dirty:
            title = f"{title} \u2022"
        self.setWindowTitle(title)

    def _autosave_tick(self):
        if not self._dirty:
            return
        self._run_autosave()

    def _run_autosave(self):
        logger.info("Autosave triggered")
        domain_masters = self.state.masters()
        issues = self.validation_service.validate(domain_masters)
        errors = [i for i in issues if i.severity == SEVERITY_ERROR]
        if errors:
            logger.warning(
                "Autosave skipped: %d validation error(s)",
                len(errors),
            )
            return
        try:
            self.sessionController.save_session(
                self.audio,
                self.sr,
                domain_masters,
            )
        except Exception:
            logger.exception("Autosave failed")
            return
        logger.info("Autosave completed")
        self._set_dirty(False)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                if self._dirty:
                    self._run_autosave()
        super().changeEvent(event)

    def closeEvent(self, event):
        self._autosave_timer.stop()
        try:
            self._unsubscribe_dirty()
        except Exception:
            pass
        try:
            self._search_unsubscribe()
        except Exception:
            pass
        try:
            self._master_updated_unsubscribe()
        except Exception:
            pass
        try:
            self._slave_updated_unsubscribe()
        except Exception:
            pass
        for window in list(self._tag_edit_windows):
            try:
                window.close()
            except RuntimeError:
                pass
        self._tag_edit_windows.clear()
        super().closeEvent(event)
