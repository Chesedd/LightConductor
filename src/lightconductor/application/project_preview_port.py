"""Narrow port for ListProjectsWithMetadataUseCase.

Exposes only what project preview needs: raw registry access
and per-project file probes. Intentionally separate from
ProjectSessionStoragePort to keep the preview use case
independent of audio/masters loading semantics.
"""
from __future__ import annotations

from typing import Any, Dict, Protocol


class ProjectPreviewPort(Protocol):
    def read_registry(self) -> Dict[str, Dict[str, Any]]:
        """Return raw registry dict (project_id -> payload).
        Empty dict on missing/corrupt registry. Must not
        raise."""
        ...

    def data_json_path(self, project_name: str) -> str:
        """Return absolute path string to project's data.json,
        regardless of existence."""
        ...

    def audio_exists(self, project_name: str) -> bool:
        """True iff the project's audio.wav file exists."""
        ...

    def project_dir_exists(self, project_name: str) -> bool:
        """True iff <projects_root>/<project_name>/ exists."""
        ...
