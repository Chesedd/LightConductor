from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Protocol

from lightconductor.domain.models import Project


class ProjectRepositoryPort(Protocol):
    def list_projects(self) -> Iterable[Project]: ...

    def save_project(self, project: Project) -> None: ...

    def delete_project(self, project_id: str) -> bool: ...

    def rename_project(self, project_id: str, new_name: str) -> bool: ...

    def export_project_to_archive(
        self,
        project_id: str,
        output_zip_path: Path | str,
    ) -> None: ...

    def import_project_from_archive(
        self,
        zip_path: Path | str,
        target_project_name: str,
    ) -> Project: ...


class ShowTransportPort(Protocol):
    def send_payload(
        self,
        pins: Dict[str, Dict[str, int]],
        payload: Dict[str, Dict[int, Dict[str, Dict[str, Any]]]],
    ) -> None: ...

    def send_start(self) -> None: ...
