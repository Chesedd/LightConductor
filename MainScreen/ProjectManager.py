import json
import os
from datetime import datetime

class ProjectManager():

    def __init__(self, storage_file="projects.json"):
        self.storage_file = storage_file
        self.projects = self.load_projects()

    def load_projects(self):
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, KeyError):
                return {}
        return {}

    def save_projects(self):
        with open(self.storage_file, 'w', encoding='utf-8') as f:
            json.dump(self.projects, f, indent=4, ensure_ascii=False)

    def add_project(self, project_data):
        project_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
        project_data['id'] = project_id
        project_data['created_at'] = datetime.now().isoformat()

        self.projects[project_id] = project_data
        self.save_projects()
        return project_id

    def delete_project(self, project_id):
        if project_id in self.projects:
            del self.projects[project_id]
            self.save_projects()
            return True
        return False

    def return_all_projects(self):
        return self.projects