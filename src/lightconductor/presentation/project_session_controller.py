from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from lightconductor.application import (
    LoadProjectSessionUseCase,
    ProjectSessionSnapshot,
    SaveProjectSessionUseCase,
)
from lightconductor.application.project_session_use_cases import ProjectSessionStoragePort
from lightconductor.domain.models import Master


@dataclass(slots=True)
class ProjectSessionController:
    storage: ProjectSessionStoragePort
    load_use_case: LoadProjectSessionUseCase = field(init=False)
    save_use_case: SaveProjectSessionUseCase = field(init=False)

    def __post_init__(self) -> None:
        self.load_use_case = LoadProjectSessionUseCase(self.storage)
        self.save_use_case = SaveProjectSessionUseCase(self.storage)

    def load_session(self) -> ProjectSessionSnapshot:
        return self.load_use_case.execute()

    def save_session(
        self,
        audio: Any,
        sample_rate: int | None,
        masters: Dict[str, Master],
    ) -> None:
        self.save_use_case.execute(audio, sample_rate, masters)
