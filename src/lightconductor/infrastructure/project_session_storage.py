"""Domain-object-based persistence for per-project data.

Replaces `LegacyProjectStorage` (will be removed in Phase 1.2.2).
Persists `Dict[str, Master]` via the unified json_mapper (PR 1.x),
wrapped in a v1 envelope (project_schema, PR 0.3), written
atomically with rotating backups (project_file_backup, PR 0.4).

This module is intentionally unused in production code during
PR 2.1a — it lives alongside the legacy storage until PR 2.2
flips the UI over.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Tuple

from lightconductor.domain.models import Master
from lightconductor.infrastructure.json_mapper import (
    pack_master,
    unpack_master,
)
from lightconductor.infrastructure.project_file_backup import (
    write_with_rotation,
)
from lightconductor.infrastructure.project_schema import (
    SchemaValidationError,
    load_and_migrate,
    unwrap_boxes,
    validate,
    wrap_boxes,
)

logger = logging.getLogger(__name__)


class ProjectSessionStorage:
    """File-system persistence for one project's session data.

    Root layout:
      <projects_root>/<project_name>/<data_filename>
      <projects_root>/<project_name>/<audio_filename>
    """

    def __init__(
        self,
        projects_root: Path | str = "Projects",
        data_filename: str = "data.json",
        audio_filename: str = "audio.wav",
    ) -> None:
        self.projects_root = Path(projects_root)
        self.data_filename = data_filename
        self.audio_filename = audio_filename

    def _project_dir(self, project_name: str) -> Path:
        return self.projects_root / project_name

    def _data_path(self, project_name: str) -> Path:
        return self._project_dir(project_name) / self.data_filename

    def _audio_path(self, project_name: str) -> Path:
        return self._project_dir(project_name) / self.audio_filename

    # --- masters ---

    def save_masters(
        self,
        project_name: str,
        masters: Dict[str, Master],
    ) -> None:
        """Pack masters, wrap as v1 envelope, validate, and write
        atomically with rotated .bak snapshots.

        Ensures the project directory exists (creates if missing,
        parents=True). Raises SchemaValidationError if the packed
        envelope fails validation (defensive — shouldn't happen in
        normal flow after json_mapper).
        """
        packed_masters = {
            master_id: pack_master(master)
            for master_id, master in masters.items()
        }
        envelope = wrap_boxes(packed_masters)
        try:
            validate(envelope)
        except SchemaValidationError:
            logger.exception(
                "Refusing to save invalid project data for %s",
                project_name,
            )
            raise
        path = self._data_path(project_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            envelope, indent=4, ensure_ascii=False,
        ).encode("utf-8")
        write_with_rotation(path, content)

    def load_masters(
        self,
        project_name: str,
    ) -> Dict[str, Master]:
        """Read data.json, migrate, validate, and unpack to domain
        Master objects.

        Returns an empty dict if the file doesn't exist. On
        SchemaValidationError: logs a warning and returns an empty
        dict (consistent with PR 0.3 behaviour).
        """
        path = self._data_path(project_name)
        if not path.exists():
            return {}
        try:
            envelope = load_and_migrate(path)
            validate(envelope)
            packed_masters = unwrap_boxes(envelope)
        except SchemaValidationError as exc:
            logger.warning(
                "data.json at %s failed schema validation: %s; "
                "returning empty project",
                path, exc,
            )
            return {}
        return {
            master_id: unpack_master(m)
            for master_id, m in packed_masters.items()
        }

    # --- audio ---

    def save_audio(
        self,
        project_name: str,
        audio: Any,
        sample_rate: int,
    ) -> None:
        """Write the audio buffer to <project>/audio.wav via
        soundfile. No-op if `audio` is None.
        """
        if audio is None:
            return
        import soundfile as sf
        path = self._audio_path(project_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), audio, sample_rate)

    def load_audio(
        self,
        project_name: str,
    ) -> Tuple[Any, int | None, str]:
        """Load via librosa. Returns (audio, sr, path_str), or
        (None, None, path_str) if the file is missing. Path is
        returned as string (not Path) — matches legacy behaviour
        consumed downstream.
        """
        path = self._audio_path(project_name)
        if not path.exists():
            return None, None, str(path)
        import librosa
        audio, sr = librosa.load(str(path), sr=None, mono=True)
        return audio, sr, str(path)
