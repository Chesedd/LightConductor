from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol, Tuple

from lightconductor.domain.models import Master


@dataclass(slots=True)
class ProjectSessionSnapshot:
    audio: Any
    sample_rate: int | None
    audio_path: str
    masters: Dict[str, Master]


class ProjectSessionStoragePort(Protocol):
    def load_audio(self) -> Tuple[Any, int | None, str]: ...

    def save_audio(self, audio: Any, sample_rate: int | None) -> None: ...

    def load_domain_masters(self) -> Dict[str, Master]: ...

    def save_domain_masters(self, masters: Dict[str, Master]) -> None: ...


@dataclass(slots=True)
class LoadProjectSessionUseCase:
    storage: ProjectSessionStoragePort

    def execute(self) -> ProjectSessionSnapshot:
        audio, sample_rate, audio_path = self.storage.load_audio()
        masters = self.storage.load_domain_masters()
        return ProjectSessionSnapshot(
            audio=audio,
            sample_rate=sample_rate,
            audio_path=audio_path,
            masters=masters,
        )


@dataclass(slots=True)
class SaveProjectSessionUseCase:
    storage: ProjectSessionStoragePort

    def execute(
        self,
        audio: Any,
        sample_rate: int | None,
        masters: Dict[str, Master],
    ) -> None:
        self.storage.save_audio(audio, sample_rate)
        self.storage.save_domain_masters(masters)
