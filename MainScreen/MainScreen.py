from MainScreen.ProjectsManager import  ProjectsManager
from PyQt6.QtWidgets import (
    QMainWindow, QPushButton, QDialog, QVBoxLayout,
    QHBoxLayout, QWidget, QLabel, QLineEdit)
from PyQt6.QtCore import pyqtSignal
from ProjectScreen.ProjectScreen import ProjectWindow

class NewProjectScreen(QDialog):
    project_created = pyqtSignal(dict)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новый проект")
        self.setModal(True)
        self.params_create()
        self.buttons_create()

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.params)
        main_layout.addWidget(self.buttons)
        self.setLayout(main_layout)

    def params_create(self):
        project_name_text = QLabel("Название проекта")
        self.project_name_bar = QLineEdit()
        project_name_layout = QHBoxLayout()
        project_name_layout.addWidget(project_name_text)
        project_name_layout.addWidget(self.project_name_bar)

        song_name_text = QLabel("Трек")
        self.song_name_bar = QLineEdit()
        song_name_layout = QHBoxLayout()
        song_name_layout.addWidget(song_name_text)
        song_name_layout.addWidget(self.song_name_bar)

        self.params = QWidget()
        params_layout = QVBoxLayout(self.params)
        params_layout.addLayout(project_name_layout)
        params_layout.addLayout(song_name_layout)

    def buttons_create(self):
        self.buttons = QWidget()
        buttons_layout = QHBoxLayout(self.buttons)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.on_ok_clicked)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(ok_btn)
        buttons_layout.addWidget(cancel_btn)

    def on_ok_clicked(self):
        data = {
            'project_name': self.project_name_bar.text(),
            'song_name': self.song_name_bar.text()
        }
        self.project_created.emit(data)
        self.accept()

class NewProjectButton(QPushButton):
    def __init__(self):
        super().__init__()

        self.setFixedHeight(80)
        self.setText("New project")

class MainWindow(QMainWindow):

    def __init__(self):
        super(MainWindow, self).__init__()
        self.setWindowTitle("LightConductor")
        self.project_system_init()
        self.showMaximized()

    def project_system_init(self):
        self.project_manager = ProjectsManager()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)
        self.layout.addStretch(1)

        button_container = QWidget()
        self.layout.addWidget(button_container)
        self.button_layout = QVBoxLayout(button_container)
        self.button_layout.setSpacing(0)
        self.button_layout.setContentsMargins(0, 0, 0, 0)

        new_project_btn = NewProjectButton()
        new_project_btn.clicked.connect(self.show_project_dialog)
        self.button_layout.addWidget(new_project_btn)

        self.project_widgets = {}
        self.load_existing_projects()

    def load_existing_projects(self):
        projects = self.project_manager.return_all_projects()
        for project_id, project_data in projects.items():
            self.create_project_widget(project_data)


    def show_project_dialog(self):
        dialog = NewProjectScreen(self)
        dialog.project_created.connect(self.create_project)
        dialog.exec()

    def create_project(self, data):
        prject_id = self.project_manager.add_project(data)

        self.create_project_widget(data)

    def create_project_widget(self, data):
        project_id = data['id']

        buttons_widget = QWidget()
        buttons_layout = QHBoxLayout(buttons_widget)
        buttons_layout.setSpacing(0)

        project_btn = QPushButton(data['project_name'])
        project_btn.setFixedHeight(60)
        project_btn.clicked.connect(lambda checked, pdata=data: self.open_project(pdata))
        buttons_layout.addWidget(project_btn)
        buttons_layout.setStretchFactor(project_btn, 10)

        rename_button = QPushButton("R")
        rename_button.setFixedHeight(60)
        buttons_layout.addWidget(rename_button)
        buttons_layout.setStretchFactor(rename_button, 1)

        delete_button = QPushButton("D")
        delete_button.setFixedHeight(60)
        delete_button.clicked.connect(lambda checked, pid=project_id: self.delete_project(pid))
        buttons_layout.addWidget(delete_button)
        buttons_layout.setStretchFactor(delete_button, 1)

        self.button_layout.insertWidget(self.button_layout.count() - 1,   buttons_widget)

        self.project_widgets[project_id] = buttons_widget

    def delete_project(self, project_id):
        if self.project_manager.delete_project(project_id):
            widget = self.project_widgets[project_id]
            self.button_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
            del self.project_widgets[project_id]
    def open_project(self, project_data):
        self.project = ProjectWindow(project_data)
        self.project.show()
        self.hide()








