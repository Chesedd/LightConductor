"""Application settings persisted to settings.json next to projects.json."""

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppSettings:
    default_master_ip: str = "192.168.0.129"
    udp_port: int = 43690
    udp_chunk_size: int = 768
    autosave_interval_seconds: int = 30
    color_presets: list = field(default_factory=list)
    recent_project_ids: list = field(default_factory=list)
    device_templates: list = field(default_factory=list)


def settings_path() -> Path:
    return Path("settings.json").resolve()


def _coerce_color_presets(value) -> list | None:
    """Return a sanitized list of [r,g,b] int triplets, or None if
    value is not a valid presets payload.

    Only accepts a list whose every entry is a list/tuple of exactly
    3 integers (not bools), each in [0, 255]. Returns a fresh list of
    fresh [r,g,b] lists; never returns the input object by reference.
    """
    if not isinstance(value, list):
        return None
    result = []
    for entry in value:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            return None
        normalized = []
        for component in entry:
            if isinstance(component, bool):
                return None
            if not isinstance(component, int):
                return None
            if component < 0 or component > 255:
                return None
            normalized.append(component)
        result.append(normalized)
    return result


def _coerce_recent_project_ids(value) -> list | None:
    """Return a sanitized list of non-empty string ids, or
    None if the payload is invalid.

    Accepts a list whose every entry is a non-empty string.
    Deduplicates while preserving order (first occurrence
    wins). Returns a fresh list. Does NOT enforce capacity;
    capacity is a controller-level concern.
    """
    if not isinstance(value, list):
        return None
    seen: set[str] = set()
    result: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            return None
        if not entry:
            return None
        if entry in seen:
            continue
        seen.add(entry)
        result.append(entry)
    return result


def _coerce_device_templates(value) -> list | None:
    """Return a sanitized list of template dicts, or None
    if the payload is invalid.

    Each entry must be a dict containing:
        - template_version: int == 1 (strict)
        - template_id: non-empty str
        - template_name: str (empty allowed; UI shows
          "(unnamed)")
        - slave_config: dict
    Deduplication by template_id (first occurrence wins).
    Unknown extra keys are preserved. Returns a fresh list
    of fresh dicts.
    """
    if not isinstance(value, list):
        return None
    seen_ids: set[str] = set()
    result: list[dict] = []
    for entry in value:
        if not isinstance(entry, dict):
            return None
        version = entry.get("template_version")
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version != 1
        ):
            return None
        tid = entry.get("template_id")
        if not isinstance(tid, str) or not tid:
            return None
        tname = entry.get("template_name")
        if not isinstance(tname, str):
            return None
        slave_cfg = entry.get("slave_config")
        if not isinstance(slave_cfg, dict):
            return None
        if tid in seen_ids:
            continue
        seen_ids.add(tid)
        result.append(dict(entry))
    return result


def _from_dict(data: object) -> AppSettings:
    defaults = AppSettings()
    if not isinstance(data, dict):
        logger.warning("settings payload is not a JSON object; using defaults")
        return defaults

    known = {f.name: f.type for f in fields(AppSettings)}
    kwargs: dict[str, object] = {}
    for name, expected_type in known.items():
        if name not in data:
            continue
        value = data[name]
        if name == "color_presets":
            coerced = _coerce_color_presets(value)
            if coerced is None:
                logger.warning(
                    "settings field %r is malformed; using default",
                    name,
                )
                continue
            kwargs[name] = coerced
            continue
        if name == "recent_project_ids":
            coerced = _coerce_recent_project_ids(value)
            if coerced is None:
                logger.warning(
                    "settings field %r is malformed; using default",
                    name,
                )
                continue
            kwargs[name] = coerced
            continue
        if name == "device_templates":
            coerced = _coerce_device_templates(value)
            if coerced is None:
                logger.warning(
                    "settings field %r is malformed; using default",
                    name,
                )
                continue
            kwargs[name] = coerced
            continue
        if not isinstance(value, expected_type):
            logger.warning(
                "settings field %r has wrong type %s; using default",
                name,
                type(value).__name__,
            )
            continue
        if expected_type is int and isinstance(value, bool):
            logger.warning("settings field %r is bool, expected int; using default", name)
            continue
        if name == "autosave_interval_seconds" and value <= 0:
            logger.warning(
                "settings field %r must be positive; using default",
                name,
            )
            continue
        kwargs[name] = value
    return AppSettings(**kwargs)


def load_settings(path: Path | None = None) -> AppSettings:
    path = path or settings_path()
    if not path.exists():
        logger.info("settings file not found; created with defaults at %s", path)
        save_settings(AppSettings(), path)
        return AppSettings()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("failed to load settings from %s: %s; using defaults", path, exc)
        return AppSettings()
    except Exception as exc:
        logger.warning("failed to load settings from %s: %s; using defaults", path, exc)
        return AppSettings()
    return _from_dict(data)


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    path = path or settings_path()
    try:
        payload = json.dumps(asdict(settings), indent=2, ensure_ascii=False) + "\n"
        path.write_text(payload, encoding="utf-8")
    except OSError:
        logger.exception("failed to save settings to %s", path)
