"""Adapter that bridges the UI to the domain-based ProjectSessionStorage.

Implements ProjectSessionStoragePort with the no-argument method
shape the UI layer expects. Holds `project_name` from construction;
delegates to `ProjectSessionStorage` and `UiMastersMapper`.

Replaces `LegacyProjectStorage`.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from lightconductor.infrastructure.json_mapper import pack_master
from lightconductor.infrastructure.project_session_storage import (
    ProjectSessionStorage,
)
from lightconductor.infrastructure.ui_masters_mapper import (
    UiMastersMapper,
)


class UiSessionBridge:
    """Per-project session storage adapter for UI consumers."""

    def __init__(
        self,
        domain_storage: ProjectSessionStorage,
        project_name: str,
        ui_mapper: UiMastersMapper,
    ) -> None:
        self._storage = domain_storage
        self._project_name = project_name
        self._ui_mapper = ui_mapper

    def load_audio(self) -> Tuple[Any, int | None, str]:
        return self._storage.load_audio(self._project_name)

    def load_boxes(self) -> Dict[str, dict]:
        masters = self._storage.load_masters(self._project_name)
        return {
            master_id: pack_master(master)
            for master_id, master in masters.items()
        }

    def save_audio(self, audio: Any, sample_rate: int | None) -> None:
        self._storage.save_audio(
            self._project_name, audio, sample_rate,
        )

    def save_boxes(self, masters: Dict[str, Any]) -> None:
        domain_masters = self._ui_mapper.map_masters(masters)
        self._storage.save_masters(
            self._project_name, domain_masters,
        )
