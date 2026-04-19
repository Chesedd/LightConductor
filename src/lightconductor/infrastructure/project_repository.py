"""Domain-object-based registry for projects.json.

Replaces `LegacyProjectsRepository` (will be removed in PR 2.2).
Persists a flat dict[project_id, metadata] keyed structure
compatible with the legacy format - no schema_version envelope
(projects.json is tiny and not versioned; see roadmap 27-28
which versioning targets only data.json).

This module is intentionally unused in production during PR 2.1b.
UI wiring happens in PR 2.2.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from lightconductor.domain.models import Project

logger = logging.getLogger(__name__)


class ProjectRepository:
    """File-system registry for the project list.

    Root layout:
      <projects_json_path>                    # the registry file
      <projects_root>/<project_name>/         # per-project dir
    """

    def __init__(
        self,
        projects_json_path: Path | str = "projects.json",
        projects_root: Path | str = "Projects",
    ) -> None:
        self.projects_json_path = Path(projects_json_path)
        self.projects_root = Path(projects_root)

    # --- internal helpers ---

    def _read_registry(self) -> Dict[str, Dict[str, Any]]:
        """Return the raw dict from projects.json.

        Empty dict if file missing. Empty dict on corruption
        (JSONDecodeError / OSError) with a warning log.
        File is NOT rewritten on corruption.
        """
        if not self.projects_json_path.exists():
            return {}
        try:
            with self.projects_json_path.open(
                "r", encoding="utf-8"
            ) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "projects.json at %s failed to load: %s; "
                "returning empty registry",
                self.projects_json_path, exc,
            )
            return {}
        if not isinstance(data, dict):
            logger.warning(
                "projects.json at %s is not a dict (got %s); "
                "returning empty registry",
                self.projects_json_path, type(data).__name__,
            )
            return {}
        return data

    def _write_registry(self, data: Dict[str, Dict[str, Any]]) -> None:
        """Write the registry atomically enough for this file type.

        No .bak rotation: projects.json is not bulky user data, and
        roadmap backups apply to data.json only. Partial writes are
        avoided via tmp file + fsync + os.replace.
        """
        self.projects_json_path.parent.mkdir(
            parents=True, exist_ok=True
        )
        tmp = self.projects_json_path.with_suffix(
            self.projects_json_path.suffix + ".tmp"
        )
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.projects_json_path)
        except Exception:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise

    def _project_dir(self, project_name: str) -> Path:
        return self.projects_root / project_name

    def _payload_to_project(
        self, project_id: str, payload: Dict[str, Any]
    ) -> Project:
        return Project(
            id=project_id,
            name=payload.get("project_name", ""),
            song_name=payload.get("song_name", ""),
        )

    # --- public API (implements ProjectRepositoryPort) ---

    def list_projects(self) -> List[Project]:
        """Return projects whose directory actually exists.

        Orphan registry entries (no matching directory) are silently
        filtered out - matches legacy behaviour.
        """
        registry = self._read_registry()
        result: List[Project] = []
        for project_id, payload in registry.items():
            if not isinstance(payload, dict):
                logger.warning(
                    "projects.json entry %s is not a dict (got %s); "
                    "skipping",
                    project_id, type(payload).__name__,
                )
                continue
            name = payload.get("project_name")
            if not name:
                logger.warning(
                    "projects.json entry %s has no project_name; skipping",
                    project_id,
                )
                continue
            if not self._project_dir(name).exists():
                continue
            result.append(self._payload_to_project(project_id, payload))
        return result

    def save_project(self, project: Project) -> None:
        """Idempotently persist a project.

        - Creates <projects_root>/<name>/ via mkdir(parents=True, exist_ok=True).
        - Adds / updates registry entry. `created_at` is set on
          first insert and preserved across updates.
        """
        self._project_dir(project.name).mkdir(
            parents=True, exist_ok=True
        )
        registry = self._read_registry()
        existing = registry.get(project.id, {})
        if not isinstance(existing, dict):
            existing = {}
        created_at = existing.get("created_at") or \
            datetime.now().isoformat()
        registry[project.id] = {
            "id": project.id,
            "project_name": project.name,
            "song_name": project.song_name,
            "created_at": created_at,
        }
        self._write_registry(registry)

    def delete_project(self, project_id: str) -> bool:
        """Remove registry entry and best-effort-delete directory.

        Returns True if the entry existed (and was removed), False
        otherwise. Directory removal is tolerant: uses
        shutil.rmtree(..., ignore_errors=True) so a missing or
        partially-broken directory does not prevent deletion of the
        registry entry.
        """
        registry = self._read_registry()
        payload = registry.get(project_id)
        if payload is None:
            return False
        name = payload.get("project_name") \
            if isinstance(payload, dict) else None
        del registry[project_id]
        if name:
            shutil.rmtree(
                self._project_dir(name), ignore_errors=True
            )
        self._write_registry(registry)
        return True
