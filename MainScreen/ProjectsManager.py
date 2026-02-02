import json
import os
import shutil
from datetime import datetime

class ProjectsManager():

    def __init__(self, storage_file="projects.json"):
        self.storage_file = storage_file
        self.projects = self.loadProjects()

    #выгрузка проектов из json файла
    def loadProjects(self):
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    projectsData = json.load(f)
                    returnData = {}
                    for projId in projectsData:
                        if os.path.exists(f"Projects/{projectsData[projId]['project_name']}"):
                            returnData[projId] = projectsData[projId]
                    return returnData
            except (json.JSONDecodeError, KeyError):
                return {}
        return {}

    #сохранение проектов в json файле
    def saveProjects(self):
        with open(self.storage_file, 'w', encoding='utf-8') as f:
            json.dump(self.projects, f, indent=4, ensure_ascii=False)

    #обавление инициализированного проекта
    def addProject(self, project_data):
        project_data['created_at'] = datetime.now().isoformat()
        os.mkdir(f"Projects/{project_data['project_name']}")

        self.projects[project_data["id"]] = project_data
        self.saveProjects()
        return

    def deleteProject(self, project_id):
        if project_id in self.projects:
            projectName = self.projects[project_id]["project_name"]
            shutil.rmtree(f"Projects/{projectName}")
            del self.projects[project_id]
            self.saveProjects()
            return True
        return False

    def returnAllProjects(self):
        return self.projects