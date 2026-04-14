from __future__ import annotations

from typing import Iterable

from MainScreen.ProjectsManager import ProjectsManager
from lightconductor.domain.models import Project


class LegacyProjectsRepository:
    """Adapter over current ProjectsManager for application use-cases."""

    def __init__(self, manager: ProjectsManager | None = None):
        self.manager = manager or ProjectsManager()

    def list_projects(self) -> Iterable[Project]:
        projects = self.manager.returnAllProjects()
        for project_id, payload in projects.items():
            yield Project(
                id=project_id,
                name=payload.get("project_name", ""),
                song_name=payload.get("song_name", ""),
            )

    def save_project(self, project: Project) -> None:
        self.manager.addProject(
            {
                "id": project.id,
                "project_name": project.name,
                "song_name": project.song_name,
            }
        )

    def delete_project(self, project_id: str) -> bool:
        return self.manager.deleteProject(project_id)
