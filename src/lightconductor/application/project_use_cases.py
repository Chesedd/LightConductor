from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from lightconductor.application.ports import ProjectRepositoryPort
from lightconductor.domain.models import Project


@dataclass(slots=True)
class ListProjectsUseCase:
    repository: ProjectRepositoryPort

    def execute(self) -> Iterable[Project]:
        return self.repository.list_projects()


@dataclass(slots=True)
class CreateProjectUseCase:
    repository: ProjectRepositoryPort

    def execute(self, name: str, song_name: str = "") -> Project:
        project = Project(
            id=datetime.now().strftime("%Y%m%d%H%M%S%f"),
            name=name,
            song_name=song_name,
        )
        self.repository.save_project(project)
        return project


@dataclass(slots=True)
class DeleteProjectUseCase:
    repository: ProjectRepositoryPort

    def execute(self, project_id: str) -> bool:
        return self.repository.delete_project(project_id)


@dataclass(slots=True)
class RenameProjectUseCase:
    repository: ProjectRepositoryPort

    def execute(self, project_id: str, new_name: str) -> bool:
        return self.repository.rename_project(project_id, new_name)


@dataclass(slots=True)
class ExportProjectUseCase:
    repository: ProjectRepositoryPort

    def execute(
        self,
        project_id: str,
        output_zip_path,
    ) -> None:
        self.repository.export_project_to_archive(
            project_id,
            output_zip_path,
        )


@dataclass(slots=True)
class ImportProjectUseCase:
    repository: ProjectRepositoryPort

    def execute(
        self,
        zip_path,
        target_project_name: str,
    ) -> Project:
        return self.repository.import_project_from_archive(
            zip_path,
            target_project_name,
        )
