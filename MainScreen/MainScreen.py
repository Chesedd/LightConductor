from PyQt6.QtWidgets import (
    QMainWindow, QPushButton, QVBoxLayout,
    QHBoxLayout, QWidget)
from PyQt6.QtCore import pyqtSignal
from ProjectScreen.ProjectScreen import ProjectWindow
from AssistanceTools.SimpleDialog import SimpleDialog
from lightconductor.infrastructure import LegacyProjectsRepository
from lightconductor.presentation import MainScreenController

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

class MainWindow(QMainWindow):

    def __init__(self):
        super(MainWindow, self).__init__()

        self.controller = MainScreenController(LegacyProjectsRepository())
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
        self.layout.addStretch(1)

        self.createUIButtons()

    #создание пространства под кнопки и кнопки нового проекта
    def createUIButtons(self):
        buttonContainer = QWidget()
        self.buttonLayout = QVBoxLayout(buttonContainer)
        self.layout.addWidget(buttonContainer)
        self.buttonLayout.setSpacing(0)
        self.buttonLayout.setContentsMargins(0, 0, 0, 0)

        newProjectBtn = QPushButton("New project")
        newProjectBtn.setFixedHeight(80)
        newProjectBtn.clicked.connect(self.showProjectDialog)
        self.buttonLayout.addWidget(newProjectBtn)

    #Загрузка существующих проектов
    def loadExistingProjects(self):
        projects = self.controller.list_projects()
        for project in projects:
            self.initProject(project, persist=False)

    #открытие диалога нового проекта
    def showProjectDialog(self):
        dialog = NewProjectScreen(self)
        dialog.projectCreated.connect(self.createAndInitProject)
        dialog.exec()

    def createAndInitProject(self, data):
        project = self.controller.create_project(data["project_name"], data["song_name"])
        self.initProject(project, persist=False)

    #создание нового проекта/инициализация старого
    def initProject(self, data, persist=False):
        buttonsWidget = QWidget()
        buttonsLayout = QHBoxLayout(buttonsWidget)
        buttonsLayout.setSpacing(0)

        projectBtn = self.createProjectButton(data['project_name'], buttonsLayout, 10)
        projectBtn.clicked.connect(lambda checked, pdata=data: self.openProject(pdata))

        renameButton = self.createProjectButton('Rename', buttonsLayout, 1)

        deleteButton = self.createProjectButton("Delete", buttonsLayout, 1)
        deleteButton.clicked.connect(lambda checked, pid=data['id']: self.deleteProject(pid))

        self.buttonLayout.insertWidget(self.buttonLayout.count() - 1, buttonsWidget)

        self.projectWidgets[data['id']] = buttonsWidget

    #создание кнопки для бокса проектных кнопок
    def createProjectButton(self, text, buttonLayout, stretch):
        button = QPushButton(text)
        button.setFixedHeight(60)
        buttonLayout.addWidget(button)
        buttonLayout.setStretchFactor(button, stretch)
        return button

    #удаление проекта
    def deleteProject(self, projectId):
        if self.controller.delete_project(projectId):
            widget = self.projectWidgets[projectId]
            self.buttonLayout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
            del self.projectWidgets[projectId]

    #открытие проекта
    def openProject(self, project_data):
        self.project = ProjectWindow(project_data)
        self.project.show()
        self.hide()







