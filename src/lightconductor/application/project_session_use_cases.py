from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol

from lightconductor.domain.models import Master


@dataclass(slots=True)
class ProjectSessionSnapshot:
    audio: Any
    sample_rate: int | None
    audio_path: str
    boxes: Dict[str, dict]


class ProjectSessionStoragePort(Protocol):
    def load_audio(self):
        ...

    def load_boxes(self) -> Dict[str, dict]:
        ...

    def save_audio(self, audio: Any, sample_rate: int | None) -> None:
        ...

    def save_boxes(self, masters: Dict[str, Any]) -> None:
        ...

    def load_domain_masters(self) -> Dict[str, Master]:
        ...

    def save_domain_masters(self, masters: Dict[str, Master]) -> None:
        ...


@dataclass(slots=True)
class LoadProjectSessionUseCase:
    storage: ProjectSessionStoragePort

    def execute(self) -> ProjectSessionSnapshot:
        audio, sample_rate, audio_path = self.storage.load_audio()
        boxes = self.storage.load_boxes()
        return ProjectSessionSnapshot(audio=audio, sample_rate=sample_rate, audio_path=audio_path, boxes=boxes)


@dataclass(slots=True)
class SaveProjectSessionUseCase:
    storage: ProjectSessionStoragePort

    def execute(self, audio: Any, sample_rate: int | None, masters: Dict[str, Any]) -> None:
        self.storage.save_audio(audio, sample_rate)
        self.storage.save_boxes(masters)


@dataclass(slots=True)
class SaveProjectSessionDomainUseCase:
    storage: ProjectSessionStoragePort

    def execute(
        self,
        audio: Any,
        sample_rate: int | None,
        masters: Dict[str, Master],
    ) -> None:
        self.storage.save_audio(audio, sample_rate)
        self.storage.save_domain_masters(masters)
