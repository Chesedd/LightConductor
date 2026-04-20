from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from lightconductor.application import (
    CreateProjectUseCase,
    DeleteProjectUseCase,
    ExportProjectUseCase,
    ImportProjectUseCase,
    ListProjectsUseCase,
    RenameProjectUseCase,
)
from lightconductor.application.ports import ProjectRepositoryPort
from lightconductor.application.project_metadata_use_case import (
    ListProjectsWithMetadataUseCase,
)
from lightconductor.config import AppSettings, save_settings

logger = logging.getLogger(__name__)

RECENT_LIMIT = 5


@dataclass(slots=True)
class MainScreenController:
    repository: ProjectRepositoryPort
    settings: Optional[AppSettings] = None
    list_projects_use_case: ListProjectsUseCase = field(init=False)
    create_project_use_case: CreateProjectUseCase = field(init=False)
    delete_project_use_case: DeleteProjectUseCase = field(init=False)
    rename_project_use_case: RenameProjectUseCase = field(init=False)
    list_with_metadata_use_case: ListProjectsWithMetadataUseCase = field(init=False)
    export_project_use_case: ExportProjectUseCase = field(init=False)
    import_project_use_case: ImportProjectUseCase = field(init=False)

    def __post_init__(self) -> None:
        self.list_projects_use_case = ListProjectsUseCase(self.repository)
        self.create_project_use_case = CreateProjectUseCase(self.repository)
        self.delete_project_use_case = DeleteProjectUseCase(self.repository)
        self.rename_project_use_case = RenameProjectUseCase(self.repository)
        self.list_with_metadata_use_case = ListProjectsWithMetadataUseCase(
            self.repository
        )
        self.export_project_use_case = ExportProjectUseCase(self.repository)
        self.import_project_use_case = ImportProjectUseCase(self.repository)

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
        result = self.delete_project_use_case.execute(project_id)
        if result and self.settings is not None:
            ids = self.settings.recent_project_ids or []
            if project_id in ids:
                self.settings.recent_project_ids = [i for i in ids if i != project_id]
                self._persist_settings()
        return result

    def rename_project(self, project_id: str, new_name: str) -> bool:
        return self.rename_project_use_case.execute(
            project_id,
            new_name,
        )

    def export_project(
        self,
        project_id: str,
        output_zip_path,
    ) -> None:
        self.export_project_use_case.execute(
            project_id,
            output_zip_path,
        )

    def import_project(
        self,
        zip_path,
        target_project_name: str,
    ) -> dict:
        """Returns dict with the same shape as create_project."""
        project = self.import_project_use_case.execute(
            zip_path,
            target_project_name,
        )
        return {
            "id": project.id,
            "project_name": project.name,
            "song_name": project.song_name,
        }

    def inspect_archive_manifest(self, zip_path) -> dict:
        """Read an archive's manifest without extracting.
        Returns a dict with keys:
            source_project_name, song_name,
            source_created_at, has_audio.

        Raises ArchiveError (or subtype) on invalid archives.
        Raises OSError on file read failures.
        """
        from pathlib import Path

        from lightconductor.infrastructure.project_archive import (
            inspect_archive as _inspect,
        )

        inspection = _inspect(Path(zip_path))
        return {
            "source_project_name": inspection.source_project_name,
            "song_name": inspection.song_name,
            "source_created_at": inspection.source_created_at,
            "has_audio": inspection.has_audio,
        }

    def mark_project_opened(self, project_id: str) -> None:
        """Move project_id to the front of recent_project_ids,
        truncate to RECENT_LIMIT, and persist. No-op when
        settings is None or project_id is falsy."""
        if self.settings is None or not project_id:
            return
        current = list(self.settings.recent_project_ids or [])
        current = [i for i in current if i != project_id]
        current.insert(0, project_id)
        if len(current) > RECENT_LIMIT:
            current = current[:RECENT_LIMIT]
        self.settings.recent_project_ids = current
        self._persist_settings()

    def get_recent_projects(self) -> list[dict]:
        """Return metadata dicts for surviving recent
        projects, in most-recent-first order. Filters out
        ids not present in the repository. Returns [] when
        settings is None."""
        if self.settings is None:
            return []
        recent_ids = self.settings.recent_project_ids or []
        if not recent_ids:
            return []
        all_meta = {m["id"]: m for m in self.list_projects_with_metadata()}
        return [all_meta[rid] for rid in recent_ids if rid in all_meta]

    def clear_recent_projects(self) -> None:
        """Empty recent_project_ids and persist. No-op when
        settings is None."""
        if self.settings is None:
            return
        if not self.settings.recent_project_ids:
            return
        self.settings.recent_project_ids = []
        self._persist_settings()

    def _persist_settings(self) -> None:
        try:
            save_settings(self.settings)
        except Exception:
            logger.exception(
                "failed to persist settings with recent projects",
            )
