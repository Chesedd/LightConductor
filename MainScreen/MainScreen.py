from MainScreen.ProjectsManager import  ProjectsManager
from PyQt6.QtWidgets import (
    QMainWindow, QPushButton, QVBoxLayout,
    QHBoxLayout, QWidget)
from PyQt6.QtCore import pyqtSignal
from ProjectScreen.ProjectScreen import ProjectWindow
from datetime import datetime
from AssistanceTools.SimpleDialog import SimpleDialog

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

        self.projectManager = ProjectsManager() #проектный мэнеджер
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
        projects = self.projectManager.returnAllProjects()
        for projectId in projects:
            self.initProject(projects[projectId])

    #открытие диалога нового проекта
    def showProjectDialog(self):
        dialog = NewProjectScreen(self)
        dialog.projectCreated.connect(self.initProject)
        dialog.exec()

    #создание нового проекта/инициализация старого
    def initProject(self, data):
        if not data['id']:
            data['id'] = datetime.now().strftime("%Y%m%d%H%M%S%f")
            self.projectManager.addProject(data)

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
        if self.projectManager.deleteProject(projectId):
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








