"""ListProjectsWithMetadataUseCase.

Reads the registry, probes per-project artefacts, builds
ProjectMetadata for each. Tolerant to per-project failures.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from lightconductor.application.project_metadata import (
    ProjectMetadata,
)
from lightconductor.application.project_preview_port import (
    ProjectPreviewPort,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ListProjectsWithMetadataUseCase:
    repository: ProjectPreviewPort

    def execute(self) -> List[ProjectMetadata]:
        raw = self.repository.read_registry()
        results: List[ProjectMetadata] = []
        for project_id, payload in raw.items():
            if not isinstance(payload, dict):
                logger.warning(
                    "projects.json entry %s has non-dict payload; "
                    "skipping",
                    project_id,
                )
                continue
            project_name = payload.get("project_name")
            if not project_name or not isinstance(project_name, str):
                logger.warning(
                    "projects.json entry %s has no project_name; "
                    "skipping",
                    project_id,
                )
                continue
            if not self.repository.project_dir_exists(project_name):
                continue
            song_name = payload.get("song_name") or ""
            created_at = payload.get("created_at")
            if not isinstance(created_at, str):
                created_at = None
            masters_count, slaves_count, modified_at = (
                self._read_data_json_metadata(project_name)
            )
            track_present = False
            try:
                track_present = bool(
                    self.repository.audio_exists(project_name)
                )
            except Exception:
                logger.warning(
                    "audio_exists probe failed for %s",
                    project_name, exc_info=True,
                )
                track_present = False
            results.append(ProjectMetadata(
                id=project_id,
                project_name=project_name,
                song_name=song_name,
                created_at=created_at,
                modified_at=modified_at,
                masters_count=masters_count,
                slaves_count=slaves_count,
                track_present=track_present,
            ))
        return results

    def _read_data_json_metadata(self, project_name: str):
        """Return (masters_count, slaves_count, modified_at)
        from the project's data.json. Any failure yields
        (0, 0, None)."""
        try:
            path_str = self.repository.data_json_path(project_name)
        except Exception:
            logger.warning(
                "data_json_path failed for %s", project_name,
                exc_info=True,
            )
            return 0, 0, None
        path = Path(path_str)
        if not path.exists():
            return 0, 0, None
        try:
            mtime = datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc,
            ).isoformat()
        except OSError:
            mtime = None
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.warning(
                "cannot read data.json for %s; counts=0",
                project_name, exc_info=True,
            )
            return 0, 0, mtime
        masters_count, slaves_count = self._count_from_envelope(data)
        return masters_count, slaves_count, mtime

    @staticmethod
    def _count_from_envelope(data) -> tuple[int, int]:
        """Count masters and slaves in a v1 envelope or a
        legacy pre-envelope dict. Non-dict payloads return
        (0, 0). Unknown shapes return (0, 0) without raising."""
        if not isinstance(data, dict):
            return 0, 0
        masters = data.get("masters") if "schema_version" in data else data
        if not isinstance(masters, dict):
            return 0, 0
        m_count = 0
        s_count = 0
        for master in masters.values():
            if not isinstance(master, dict):
                continue
            m_count += 1
            slaves = master.get("slaves")
            if isinstance(slaves, dict):
                s_count += len(slaves)
        return m_count, s_count
