from __future__ import annotations

from typing import Dict, Iterable, Protocol

from lightconductor.domain.models import Project


class ProjectRepositoryPort(Protocol):
    def list_projects(self) -> Iterable[Project]:
        ...

    def save_project(self, project: Project) -> None:
        ...

    def delete_project(self, project_id: str) -> bool:
        ...

    def rename_project(self, project_id: str, new_name: str) -> bool:
        ...


class ShowTransportPort(Protocol):
    def send_payload(self, pins: Dict[str, Dict[str, int]], payload: Dict[str, Dict[int, Dict[str, dict]]]) -> None:
        ...

    def send_start(self) -> None:
        ...
