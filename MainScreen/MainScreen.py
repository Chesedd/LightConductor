from PyQt6.QtWidgets import (
    QMainWindow, QPushButton, QVBoxLayout,
    QHBoxLayout, QWidget, QLabel, QMessageBox,
    QDialog, QLineEdit, QFrame,
)
from PyQt6.QtCore import pyqtSignal
from ProjectScreen.ProjectScreen import ProjectWindow
from AssistanceTools.SimpleDialog import SimpleDialog
from MainScreen.ProjectCard import ProjectCard
from lightconductor.config import load_settings
from lightconductor.infrastructure.project_repository import ProjectRepository
from lightconductor.presentation.main_controller import MainScreenController

class NewProjectScreen(SimpleDialog):
    projectCreated = pyqtSignal(dict)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новый проект")
        self.setModal(True)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)

        self.paramsCreate()
        self.buttonsCreate()

    #создание баров под название и трек
    def paramsCreate(self):
        self.projectNameBar = self.LabelAndLine("Название проекта")
        self.songNameBar = self.LabelAndLine("Трек")


    #создание ok и cancel
    def buttonsCreate(self):
        okBtn = self.OkAndCancel()
        okBtn.clicked.connect(self.onOkClicked)

    def onOkClicked(self):
        data = {
            'project_name': self.projectNameBar.text(),
            'song_name': self.songNameBar.text(),
            'id': ''
        }
        self.projectCreated.emit(data)
        self.accept()


class RenameProjectDialog(QDialog):
    def __init__(self, current_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename project")
        self.setModal(True)
        layout = QVBoxLayout(self)
        label = QLabel("New project name:")
        self._name_edit = QLineEdit(current_name)
        self._name_edit.selectAll()
        button_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        button_row.addStretch(1)
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)
        layout.addWidget(label)
        layout.addWidget(self._name_edit)
        layout.addLayout(button_row)

    def new_name(self) -> str:
        return self._name_edit.text()


class MainWindow(QMainWindow):

    def __init__(self):
        super(MainWindow, self).__init__()

        self.settings = load_settings()
        self.controller = MainScreenController(
            ProjectRepository(), settings=self.settings,
        )
        self.projectWidgets = {} # айди проекта -> бокс с кнопками

        self.initUI()
        self.loadExistingProjects()
        self.showMaximized()

    #инициализация интерфейса
    def initUI(self):
        self.setWindowTitle("LightConductor")

        centralWidget = QWidget()
        self.setCentralWidget(centralWidget)
        self.layout = QVBoxLayout(centralWidget)
        self.layout.setContentsMargins(24, 24, 24, 24)
        self.layout.setSpacing(12)

        title = QLabel("LightConductor Projects")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.layout.addWidget(title)

        self._init_recent_section()
        self.createUIButtons()
        self.layout.addStretch(1)

    #создание пространства под кнопки и кнопки нового проекта
    def createUIButtons(self):
        buttonContainer = QWidget()
        self.buttonLayout = QVBoxLayout(buttonContainer)
        self.layout.addWidget(buttonContainer)
        self.buttonLayout.setSpacing(10)
        self.buttonLayout.setContentsMargins(0, 0, 0, 0)

        newProjectBtn = QPushButton("New project")
        newProjectBtn.setFixedHeight(52)
        newProjectBtn.clicked.connect(self.showProjectDialog)
        self.buttonLayout.addWidget(newProjectBtn)

    #Загрузка существующих проектов
    def loadExistingProjects(self):
        projects = self.controller.list_projects_with_metadata()
        for project in projects:
            self.initProject(project)

    #открытие диалога нового проекта
    def showProjectDialog(self):
        dialog = NewProjectScreen(self)
        dialog.projectCreated.connect(self.createAndInitProject)
        dialog.exec()

    def createAndInitProject(self, data):
        project = self.controller.create_project(
            data["project_name"], data["song_name"],
        )
        all_meta = {
            m["id"]: m
            for m in self.controller.list_projects_with_metadata()
        }
        metadata = all_meta.get(project["id"], {
            "id": project["id"],
            "project_name": project["project_name"],
            "song_name": project["song_name"],
            "created_at": None,
            "modified_at": None,
            "masters_count": 0,
            "slaves_count": 0,
            "track_present": False,
        })
        self.initProject(metadata)

    def initProject(self, data: dict):
        card = ProjectCard(metadata=data, parent=self)
        card.openRequested.connect(self._on_open_requested)
        card.renameRequested.connect(self._on_rename_requested)
        card.deleteRequested.connect(self._on_delete_requested)
        self.buttonLayout.insertWidget(
            self.buttonLayout.count() - 1, card,
        )
        self.projectWidgets[data["id"]] = card

    def _on_open_requested(self, project_id: str):
        card = self.projectWidgets.get(project_id)
        if card is None:
            return
        self.openProject({
            "id": card.project_id(),
            "project_name": card.project_name(),
        })

    def _on_rename_requested(self, project_id: str):
        card = self.projectWidgets.get(project_id)
        if card is None:
            return
        dialog = RenameProjectDialog(card.project_name(), self)
        while True:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            new_name = dialog.new_name().strip()
            if not new_name:
                QMessageBox.warning(
                    self, "Invalid name",
                    "Project name cannot be empty.",
                )
                continue
            if any(sep in new_name for sep in ("/", "\\")):
                QMessageBox.warning(
                    self, "Invalid name",
                    "Project name cannot contain path separators.",
                )
                continue
            try:
                ok = self.controller.rename_project(
                    project_id, new_name,
                )
            except Exception:
                ok = False
            if not ok:
                QMessageBox.warning(
                    self, "Rename failed",
                    "Could not rename project. The name may "
                    "be in use or the filesystem blocked the "
                    "operation.",
                )
                continue
            all_meta = {
                m["id"]: m
                for m in self.controller.list_projects_with_metadata()
            }
            if project_id in all_meta:
                card.update_metadata(all_meta[project_id])
            return

    def _on_delete_requested(self, project_id: str):
        card = self.projectWidgets.get(project_id)
        if card is None:
            return
        reply = QMessageBox.question(
            self, "Delete project",
            f"Delete project \"{card.project_name()}\"? "
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.deleteProject(project_id)

    #удаление проекта
    def deleteProject(self, projectId):
        if self.controller.delete_project(projectId):
            widget = self.projectWidgets[projectId]
            self.buttonLayout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
            del self.projectWidgets[projectId]
            self._refresh_recent_section()

    #открытие проекта
    def openProject(self, project_data):
        self.controller.mark_project_opened(
            project_data.get("id", ""),
        )
        self._refresh_recent_section()
        self.project = ProjectWindow(project_data)
        self.project.show()
        self.hide()

    def _init_recent_section(self) -> None:
        """Build the Recent section. Hidden until populated."""
        self._recentFrame = QFrame()
        self._recentFrame.setFrameShape(QFrame.Shape.StyledPanel)
        self._recentFrame.setStyleSheet(
            "QFrame { border: 1px solid #2e353d; border-radius: 10px; }"
        )
        outer = QVBoxLayout(self._recentFrame)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header = QLabel("Recent")
        header.setStyleSheet(
            "QLabel { font-size: 13px; font-weight: 600; "
            "color: #c8cfd6; border: none; }"
        )
        header_row.addWidget(header)
        header_row.addStretch(1)
        self._recentClearBtn = QPushButton("Clear")
        self._recentClearBtn.setFixedHeight(24)
        self._recentClearBtn.clicked.connect(
            self._on_clear_recent,
        )
        header_row.addWidget(self._recentClearBtn)
        outer.addLayout(header_row)

        self._recentListLayout = QVBoxLayout()
        self._recentListLayout.setContentsMargins(0, 0, 0, 0)
        self._recentListLayout.setSpacing(4)
        outer.addLayout(self._recentListLayout)

        self.layout.addWidget(self._recentFrame)
        self._refresh_recent_section()

    def _refresh_recent_section(self) -> None:
        while self._recentListLayout.count():
            item = self._recentListLayout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        recent = self.controller.get_recent_projects()
        if not recent:
            self._recentFrame.setVisible(False)
            return
        self._recentFrame.setVisible(True)
        for meta in recent:
            pid = meta.get("id", "")
            pname = meta.get("project_name", "")
            btn = QPushButton(f"\u25b6 {pname}")
            btn.setFixedHeight(30)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding-left: 10px; "
                "border: 1px solid transparent; }"
            )
            btn.clicked.connect(
                lambda _checked=False, data=dict(meta):
                    self._on_recent_clicked(data),
            )
            self._recentListLayout.addWidget(btn)

    def _on_recent_clicked(self, project_data: dict) -> None:
        self.openProject(project_data)

    def _on_clear_recent(self) -> None:
        self.controller.clear_recent_projects()
        self._refresh_recent_section()
