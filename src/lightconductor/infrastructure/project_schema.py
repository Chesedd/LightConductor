from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1


class SchemaValidationError(ValueError):
    """Raised when data.json content violates schema v1."""


_MASTER_FIELDS: Tuple[Tuple[str, Tuple[type, ...]], ...] = (
    ("name", (str,)),
    ("id", (str,)),
    ("ip", (str,)),
    ("slaves", (dict,)),
)

_SLAVE_FIELDS: Tuple[Tuple[str, Tuple[type, ...]], ...] = (
    ("name", (str,)),
    ("pin", (str, int)),
    ("led_count", (int,)),
    ("id", (str,)),
    ("tagTypes", (dict,)),
)

_TAG_TYPE_FIELDS: Tuple[Tuple[str, Tuple[type, ...]], ...] = (
    ("color", (list, str)),
    ("pin", (str, int)),
    ("segment_start", (str, int)),
    ("segment_size", (int,)),
    ("row", (int,)),
    ("table", (int,)),
    ("topology", (list,)),
    ("tags", (dict,)),
)

_TAG_FIELDS: Tuple[Tuple[str, Tuple[type, ...]], ...] = (
    ("time", (int, float)),
    ("action", (bool,)),
    ("colors", (list, str)),
)


def wrap_boxes(boxes: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a masters dict in the v1 envelope. Used on write."""
    return {"schema_version": CURRENT_SCHEMA_VERSION, "masters": boxes}


def unwrap_boxes(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return the masters dict from a validated v1 envelope."""
    return data["masters"]


def migrate_to_current(data: Any) -> Dict[str, Any]:
    """Apply migrations until data reaches CURRENT_SCHEMA_VERSION.

    - If `data` is a dict without `schema_version`, it is treated as
      v0 legacy and wrapped via wrap_boxes().
    - If `data` is already v1, returned as-is.
    - If `data` carries a version higher than CURRENT_SCHEMA_VERSION,
      SchemaValidationError is raised (prevent older code from
      silently corrupting newer files).
    """
    if not isinstance(data, dict):
        raise SchemaValidationError(
            f"top-level: expected dict, got {type(data).__name__}"
        )
    if "schema_version" not in data:
        envelope = wrap_boxes(data)
        _coerce_legacy_tag_actions(envelope)
        return envelope
    version = data["schema_version"]
    if not isinstance(version, int) or isinstance(version, bool):
        raise SchemaValidationError(
            f"schema_version: expected int, got {type(version).__name__}"
        )
    if version > CURRENT_SCHEMA_VERSION:
        raise SchemaValidationError(
            f"schema_version {version} is newer than supported "
            f"{CURRENT_SCHEMA_VERSION}; refusing to downgrade"
        )
    if version == CURRENT_SCHEMA_VERSION:
        _coerce_legacy_tag_actions(data)
        return data
    # No intermediate versions exist yet; future migrations will chain here.
    raise SchemaValidationError(f"unknown schema_version {version}")


def _coerce_legacy_tag_actions(envelope: Dict[str, Any]) -> None:
    """Normalize legacy string tag.action values to bool in-place.

    Pre-bool schemas wrote "On"/"Off" strings. Walks the envelope
    and rewrites any str tag action to its boolean equivalent:
    "On" → True, anything else (incl. "Off") → False. Non-string
    actions (already bool or malformed non-str/non-bool) are left
    untouched; schema validate() will catch the latter.
    """
    masters = envelope.get("masters")
    if not isinstance(masters, dict):
        return
    for master in masters.values():
        if not isinstance(master, dict):
            continue
        slaves = master.get("slaves")
        if not isinstance(slaves, dict):
            continue
        for slave in slaves.values():
            if not isinstance(slave, dict):
                continue
            tag_types = slave.get("tagTypes")
            if not isinstance(tag_types, dict):
                continue
            for tag_type in tag_types.values():
                if not isinstance(tag_type, dict):
                    continue
                tags = tag_type.get("tags")
                if not isinstance(tags, dict):
                    continue
                for tag in tags.values():
                    if isinstance(tag, dict):
                        action = tag.get("action")
                        if isinstance(action, str):
                            tag["action"] = action == "On"


def _format_types(types: Iterable[type]) -> str:
    return "|".join(t.__name__ for t in types)


def _check_fields(
    obj: Any,
    path: str,
    required_types: Tuple[Tuple[str, Tuple[type, ...]], ...],
) -> None:
    if not isinstance(obj, dict):
        raise SchemaValidationError(f"{path}: expected dict, got {type(obj).__name__}")
    for field, expected in required_types:
        if field not in obj:
            raise SchemaValidationError(f"{path}: missing required field '{field}'")
        value = obj[field]
        # bool is a subclass of int; reject it where we ask for int.
        if int in expected and bool not in expected and isinstance(value, bool):
            raise SchemaValidationError(
                f"{path}.{field}: expected {_format_types(expected)}, "
                f"got {type(value).__name__}"
            )
        if not isinstance(value, expected):
            raise SchemaValidationError(
                f"{path}.{field}: expected {_format_types(expected)}, "
                f"got {type(value).__name__}"
            )


def validate(data: Any) -> None:
    """Validate that `data` is a well-formed v1 envelope.

    Raises SchemaValidationError with a clear field path on violation.
    Extra (unknown) keys at any level are allowed for forward compat.
    """
    if not isinstance(data, dict):
        raise SchemaValidationError(
            f"top-level: expected dict, got {type(data).__name__}"
        )
    if "schema_version" not in data:
        raise SchemaValidationError(
            "top-level: missing required field 'schema_version'"
        )
    version = data["schema_version"]
    if not isinstance(version, int) or isinstance(version, bool):
        raise SchemaValidationError(
            f"schema_version: expected int, got {type(version).__name__}"
        )
    if version != CURRENT_SCHEMA_VERSION:
        raise SchemaValidationError(
            f"schema_version: expected {CURRENT_SCHEMA_VERSION}, got {version}"
        )
    if "masters" not in data:
        raise SchemaValidationError("top-level: missing required field 'masters'")
    masters = data["masters"]
    if not isinstance(masters, dict):
        raise SchemaValidationError(
            f"masters: expected dict, got {type(masters).__name__}"
        )

    for key in data:
        if key not in ("schema_version", "masters"):
            logger.debug("ignoring unknown top-level key %r", key)

    for master_id, master in masters.items():
        master_path = f"masters.{master_id}"
        _check_fields(master, master_path, _MASTER_FIELDS)
        for slave_id, slave in master["slaves"].items():
            slave_path = f"{master_path}.slaves.{slave_id}"
            _check_fields(slave, slave_path, _SLAVE_FIELDS)
            for type_name, tag_type in slave["tagTypes"].items():
                type_path = f"{slave_path}.tagTypes.{type_name}"
                _check_fields(tag_type, type_path, _TAG_TYPE_FIELDS)
                for tag_id, tag in tag_type["tags"].items():
                    tag_path = f"{type_path}.tags.{tag_id}"
                    _check_fields(tag, tag_path, _TAG_FIELDS)


def load_and_migrate(path: Path) -> Dict[str, Any]:
    """Read `path`, migrate, validate, return the v1 envelope.

    On json.JSONDecodeError or OSError, raises SchemaValidationError
    with the original exception chained as __cause__.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"{path}: file is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise SchemaValidationError(f"{path}: cannot read file: {exc}") from exc

    envelope = migrate_to_current(raw)
    validate(envelope)
    return envelope
