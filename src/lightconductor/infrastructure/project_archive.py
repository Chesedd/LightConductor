"""Project archive (zip) export and import.

An archive is a zip containing a flat layout of manifest.json,
data.json, and (optionally) audio.wav. This module handles
the compression/decompression and format validation.
Registry integration (collision resolution, id generation,
projects.json update) is the caller's responsibility; see
ProjectRepository in 5.5b.

Pure infrastructure: no Qt, no logging side effects at import
time. Atomic writes via tmp+fsync+os.replace.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lightconductor.infrastructure.project_schema import (
    CURRENT_SCHEMA_VERSION,
    SchemaValidationError,
    load_and_migrate,
    validate,
)

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"
DATA_FILENAME_IN_ARCHIVE = "data.json"
AUDIO_FILENAME_IN_ARCHIVE = "audio.wav"
MANIFEST_CURRENT_VERSION = 1


# --- Exceptions ---

class ArchiveError(Exception):
    """Base class for archive failures."""


class ArchiveReadError(ArchiveError):
    """Zip file cannot be opened or is corrupt."""


class ArchiveManifestMissing(ArchiveError):
    """Archive does not contain manifest.json."""


class ArchiveManifestInvalid(ArchiveError):
    """manifest.json is not valid JSON or missing fields."""


class ArchiveVersionUnsupported(ArchiveError):
    """manifest_version is newer than this code supports."""


class ArchiveDataJsonMissing(ArchiveError):
    """Archive does not contain data.json."""


class ArchiveDataJsonInvalid(ArchiveError):
    """data.json fails schema validation."""


# --- Inspection DTO ---

@dataclass(slots=True, frozen=True)
class ArchiveInspection:
    """Read-only snapshot of archive contents.

    Holds parsed manifest and byte payloads for data.json and
    audio.wav so the caller can decide whether to commit the
    import without re-opening the zip.
    """

    manifest: dict
    data_json_bytes: bytes
    audio_wav_bytes: Optional[bytes]  # None when has_audio=False

    @property
    def has_audio(self) -> bool:
        return self.audio_wav_bytes is not None

    @property
    def source_project_name(self) -> str:
        return str(self.manifest.get("source_project_name", ""))

    @property
    def song_name(self) -> str:
        return str(self.manifest.get("song_name", "") or "")

    @property
    def source_created_at(self) -> str:
        return str(self.manifest.get("source_created_at", "") or "")


# --- Helpers ---

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_zip(
    output_zip: Path,
    files: dict,  # name_in_archive -> bytes
) -> None:
    """Write a zip atomically: build under <out>.tmp, then
    os.replace. Raises on failure; cleans up tmp."""
    output_zip = Path(output_zip)
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_zip.with_suffix(output_zip.suffix + ".tmp")
    try:
        with zipfile.ZipFile(
            tmp,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as zf:
            for name, payload in files.items():
                zf.writestr(name, payload)
        try:
            fd = os.open(str(tmp), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass
        os.replace(tmp, output_zip)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


# --- Public API ---

def export_project(
    project_dir: Path,
    project_name: str,
    song_name: str,
    source_created_at: str,
    output_zip: Path,
) -> None:
    """Build a zip archive from a project directory.

    Reads project_dir/data.json (required) and
    project_dir/audio.wav (optional). Writes the zip
    atomically to output_zip, creating parents as needed.

    Raises FileNotFoundError if data.json is missing.
    Other I/O errors propagate.
    """
    project_dir = Path(project_dir)
    data_path = project_dir / "data.json"
    if not data_path.exists():
        raise FileNotFoundError(
            f"data.json not found in {project_dir}"
        )
    data_bytes = data_path.read_bytes()
    audio_path = project_dir / "audio.wav"
    has_audio = audio_path.exists()
    audio_bytes = audio_path.read_bytes() if has_audio else None

    manifest = {
        "manifest_version": MANIFEST_CURRENT_VERSION,
        "exported_at": _now_iso(),
        "source_project_name": project_name,
        "song_name": song_name or "",
        "source_created_at": source_created_at or "",
        "data_schema_version": CURRENT_SCHEMA_VERSION,
        "has_audio": has_audio,
    }
    manifest_bytes = (
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")

    files = {
        MANIFEST_FILENAME: manifest_bytes,
        DATA_FILENAME_IN_ARCHIVE: data_bytes,
    }
    if has_audio and audio_bytes is not None:
        files[AUDIO_FILENAME_IN_ARCHIVE] = audio_bytes

    _atomic_write_zip(output_zip, files)


def inspect_archive(zip_path: Path) -> ArchiveInspection:
    """Read and validate an archive without extracting to disk.

    Returns ArchiveInspection with parsed manifest and
    in-memory payloads.

    Validation steps (in order):
      1. Zip opens without error.
      2. manifest.json exists.
      3. manifest.json parses as JSON and is a dict.
      4. manifest_version is an int and <= current.
      5. data.json exists.
      6. data.json parses as JSON AND validates against
         project_schema (load_and_migrate + validate).
    Raises the specific Archive* exception on the first
    failure. Does NOT write anything to disk beyond the
    temp file used for schema validation.
    """
    zip_path = Path(zip_path)
    try:
        zf = zipfile.ZipFile(zip_path, mode="r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveReadError(
            f"cannot open {zip_path}: {exc}",
        ) from exc
    try:
        names = set(zf.namelist())
        if MANIFEST_FILENAME not in names:
            raise ArchiveManifestMissing(
                f"{zip_path}: missing {MANIFEST_FILENAME}",
            )
        try:
            manifest_bytes = zf.read(MANIFEST_FILENAME)
            manifest = json.loads(manifest_bytes)
        except (json.JSONDecodeError, KeyError) as exc:
            raise ArchiveManifestInvalid(
                f"{zip_path}: manifest.json not valid JSON: {exc}",
            ) from exc
        if not isinstance(manifest, dict):
            raise ArchiveManifestInvalid(
                f"{zip_path}: manifest.json is not a JSON object",
            )
        version = manifest.get("manifest_version")
        if not isinstance(version, int) or isinstance(version, bool):
            raise ArchiveManifestInvalid(
                f"{zip_path}: manifest_version is not an int",
            )
        if version > MANIFEST_CURRENT_VERSION:
            raise ArchiveVersionUnsupported(
                f"{zip_path}: manifest_version {version} > "
                f"supported {MANIFEST_CURRENT_VERSION}",
            )
        for field in (
            "exported_at",
            "source_project_name",
            "data_schema_version",
            "has_audio",
        ):
            if field not in manifest:
                raise ArchiveManifestInvalid(
                    f"{zip_path}: manifest missing {field!r}",
                )
        if DATA_FILENAME_IN_ARCHIVE not in names:
            raise ArchiveDataJsonMissing(
                f"{zip_path}: missing {DATA_FILENAME_IN_ARCHIVE}",
            )
        data_json_bytes = zf.read(DATA_FILENAME_IN_ARCHIVE)
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".json", delete=False,
            ) as tmp:
                tmp.write(data_json_bytes)
                tmp_path = Path(tmp.name)
            try:
                envelope = load_and_migrate(tmp_path)
                validate(envelope)
            finally:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        except SchemaValidationError as exc:
            raise ArchiveDataJsonInvalid(
                f"{zip_path}: data.json failed schema validation: {exc}",
            ) from exc
        has_audio_flag = bool(manifest.get("has_audio", False))
        audio_bytes: Optional[bytes] = None
        if has_audio_flag and AUDIO_FILENAME_IN_ARCHIVE in names:
            audio_bytes = zf.read(AUDIO_FILENAME_IN_ARCHIVE)
        elif has_audio_flag:
            raise ArchiveManifestInvalid(
                f"{zip_path}: manifest.has_audio=true but "
                f"{AUDIO_FILENAME_IN_ARCHIVE} missing",
            )
        return ArchiveInspection(
            manifest=manifest,
            data_json_bytes=data_json_bytes,
            audio_wav_bytes=audio_bytes,
        )
    finally:
        zf.close()


def extract_archive(
    inspection: ArchiveInspection,
    target_dir: Path,
) -> None:
    """Write data.json and (optional) audio.wav from a
    previously-inspected archive into target_dir. Creates
    target_dir and parents if missing. Overwrites existing
    data.json / audio.wav in target_dir without prompting.

    The caller is responsible for collision checks against
    the project registry — this function only writes files.
    """
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "data.json").write_bytes(
        inspection.data_json_bytes,
    )
    if inspection.audio_wav_bytes is not None:
        (target_dir / "audio.wav").write_bytes(
            inspection.audio_wav_bytes,
        )
