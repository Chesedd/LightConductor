from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from lightconductor.application import CreateProjectUseCase, DeleteProjectUseCase, ListProjectsUseCase
from lightconductor.application.ports import ProjectRepositoryPort


@dataclass(slots=True)
class MainScreenController:
    repository: ProjectRepositoryPort
    list_projects_use_case: ListProjectsUseCase = field(init=False)
    create_project_use_case: CreateProjectUseCase = field(init=False)
    delete_project_use_case: DeleteProjectUseCase = field(init=False)

    def __post_init__(self) -> None:
        self.list_projects_use_case = ListProjectsUseCase(self.repository)
        self.create_project_use_case = CreateProjectUseCase(self.repository)
        self.delete_project_use_case = DeleteProjectUseCase(self.repository)

    def list_projects(self) -> List[dict]:
        return [
            {
                "id": project.id,
                "project_name": project.name,
                "song_name": project.song_name,
            }
            for project in self.list_projects_use_case.execute()
        ]

    def create_project(self, project_name: str, song_name: str) -> dict:
        project = self.create_project_use_case.execute(project_name, song_name)
        return {
            "id": project.id,
            "project_name": project.name,
            "song_name": project.song_name,
        }

    def delete_project(self, project_id: str) -> bool:
        return self.delete_project_use_case.execute(project_id)
