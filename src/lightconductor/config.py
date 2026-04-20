"""Application settings persisted to settings.json next to projects.json."""

import json
import logging
from dataclasses import asdict, dataclass, fields
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppSettings:
    default_master_ip: str = "192.168.0.129"
    udp_port: int = 43690
    udp_chunk_size: int = 768
    autosave_interval_seconds: int = 30


def settings_path() -> Path:
    return Path("settings.json").resolve()


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
