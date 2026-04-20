"""Adapter that bridges the UI to the domain-based ProjectSessionStorage.

Implements ProjectSessionStoragePort with the no-argument method
shape the UI layer expects. Holds `project_name` from construction;
delegates to `ProjectSessionStorage`.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from lightconductor.domain.models import Master
from lightconductor.infrastructure.project_session_storage import (
    ProjectSessionStorage,
)


class UiSessionBridge:
    """Per-project session storage adapter for UI consumers."""

    def __init__(
        self,
        domain_storage: ProjectSessionStorage,
        project_name: str,
    ) -> None:
        self._storage = domain_storage
        self._project_name = project_name

    def load_audio(self) -> Tuple[Any, int | None, str]:
        return self._storage.load_audio(self._project_name)

    def save_audio(self, audio: Any, sample_rate: int | None) -> None:
        self._storage.save_audio(
            self._project_name,
            audio,
            sample_rate,
        )

    def load_domain_masters(self) -> Dict[str, Master]:
        """Return domain masters directly.
        Consumed by ProjectWindow to populate ProjectState."""
        return self._storage.load_masters(self._project_name)

    def save_domain_masters(self, masters: Dict[str, Master]) -> None:
        """Persist domain masters.
        Consumed by ProjectWindow from ProjectState."""
        self._storage.save_masters(self._project_name, masters)
