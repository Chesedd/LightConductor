from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from lightconductor.application import (
    CreateProjectUseCase,
    DeleteProjectUseCase,
    ListProjectsUseCase,
    RenameProjectUseCase,
)
from lightconductor.application.ports import ProjectRepositoryPort
from lightconductor.application.project_metadata_use_case import (
    ListProjectsWithMetadataUseCase,
)


@dataclass(slots=True)
class MainScreenController:
    repository: ProjectRepositoryPort
    list_projects_use_case: ListProjectsUseCase = field(init=False)
    create_project_use_case: CreateProjectUseCase = field(init=False)
    delete_project_use_case: DeleteProjectUseCase = field(init=False)
    rename_project_use_case: RenameProjectUseCase = field(init=False)
    list_with_metadata_use_case: ListProjectsWithMetadataUseCase = field(init=False)

    def __post_init__(self) -> None:
        self.list_projects_use_case = ListProjectsUseCase(self.repository)
        self.create_project_use_case = CreateProjectUseCase(self.repository)
        self.delete_project_use_case = DeleteProjectUseCase(self.repository)
        self.rename_project_use_case = RenameProjectUseCase(self.repository)
        self.list_with_metadata_use_case = (
            ListProjectsWithMetadataUseCase(self.repository)
        )

    def list_projects(self) -> List[dict]:
        return [
            {
                "id": project.id,
                "project_name": project.name,
                "song_name": project.song_name,
            }
            for project in self.list_projects_use_case.execute()
        ]

    def list_projects_with_metadata(self) -> list[dict]:
        return [
            {
                "id": m.id,
                "project_name": m.project_name,
                "song_name": m.song_name,
                "created_at": m.created_at,
                "modified_at": m.modified_at,
                "masters_count": m.masters_count,
                "slaves_count": m.slaves_count,
                "track_present": m.track_present,
            }
            for m in self.list_with_metadata_use_case.execute()
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

    def rename_project(self, project_id: str, new_name: str) -> bool:
        return self.rename_project_use_case.execute(
            project_id, new_name,
        )
