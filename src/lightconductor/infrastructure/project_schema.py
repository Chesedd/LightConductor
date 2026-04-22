from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple, cast

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 4

# Intentionally duplicated with
# ProjectScreen.TagLogic.TagTimelineController.SNAP_GRANULARITY_SECONDS:
# the schema module must be self-contained. If the UI constant ever
# changes, migration math must not silently follow.
_V4_SNAP_GRANULARITY = 0.02


class SchemaValidationError(ValueError):
    """Raised when data.json content violates the current schema."""


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
    ("grid_rows", (int,)),
    ("grid_columns", (int,)),
    ("led_cells", (list,)),
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
    """Wrap a masters dict in the current envelope. Used on write."""
    return {"schema_version": CURRENT_SCHEMA_VERSION, "masters": boxes}


def unwrap_boxes(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return the masters dict from a validated envelope."""
    return cast(Dict[str, Any], data["masters"])


def _migrate_v1_to_v2(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Add grid_rows and grid_columns to every slave in-place.

    Derives defaults from led_count (1 row × N columns) to preserve
    the invariant led_count == grid_rows * grid_columns for legacy
    slaves. If either field is already present it is left as-is.
    Bumps envelope schema_version to 2. Returns the mutated envelope.
    """
    masters = envelope.get("masters")
    if not isinstance(masters, dict):
        envelope["schema_version"] = 2
        return envelope
    for master in masters.values():
        if not isinstance(master, dict):
            continue
        slaves = master.get("slaves")
        if not isinstance(slaves, dict):
            continue
        for slave in slaves.values():
            if not isinstance(slave, dict):
                continue
            if "grid_rows" not in slave:
                slave["grid_rows"] = 1
            if "grid_columns" not in slave:
                led_count = slave.get("led_count", 0)
                try:
                    slave["grid_columns"] = int(led_count)
                except (TypeError, ValueError):
                    slave["grid_columns"] = 0
    envelope["schema_version"] = 2
    return envelope


def _migrate_v2_to_v3(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Fill led_cells for v2 slaves with [0, 1, ..., led_count-1].

    The default orders the wire linearly across the canvas cells,
    preserving pre-8.6 visual behavior where cell index and wire
    position coincide. If led_cells is already present on a slave,
    it is left untouched. Bumps envelope schema_version to 3.
    Returns the mutated envelope.
    """
    masters = envelope.get("masters")
    if not isinstance(masters, dict):
        envelope["schema_version"] = 3
        return envelope
    for master in masters.values():
        if not isinstance(master, dict):
            continue
        slaves = master.get("slaves")
        if not isinstance(slaves, dict):
            continue
        for slave in slaves.values():
            if not isinstance(slave, dict):
                continue
            if "led_cells" not in slave:
                led_count = slave.get("led_count", 0)
                try:
                    n = int(led_count)
                except (TypeError, ValueError):
                    n = 0
                slave["led_cells"] = list(range(max(0, n)))
    envelope["schema_version"] = 3
    return envelope


def _migrate_v3_to_v4(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Snap every tag.time to the nearest _V4_SNAP_GRANULARITY (0.02s).

    Walks masters → slaves → tagTypes → tags. For each tag, rounds
    its `time` field to the nearest multiple of 0.02. Existing
    0.1-grid tags land cleanly because 0.1 is an integer multiple
    of 0.02. After rounding, if two tags within the same
    (master, slave, tag_type) collapse to the same time, the first
    one in iteration order is kept; subsequent collisions are
    dropped with a per-drop warning. Bumps envelope schema_version
    to 4. Returns the mutated envelope.
    """
    masters = envelope.get("masters")
    if not isinstance(masters, dict):
        envelope["schema_version"] = 4
        return envelope
    for master_id, master in masters.items():
        if not isinstance(master, dict):
            continue
        slaves = master.get("slaves")
        if not isinstance(slaves, dict):
            continue
        for slave_id, slave in slaves.items():
            if not isinstance(slave, dict):
                continue
            tag_types = slave.get("tagTypes")
            if not isinstance(tag_types, dict):
                continue
            for tag_type_name, tag_type in tag_types.items():
                if not isinstance(tag_type, dict):
                    continue
                tags = tag_type.get("tags")
                if not isinstance(tags, dict):
                    continue
                seen: Dict[float, Any] = {}
                kept: Dict[Any, Any] = {}
                for tag_key, tag in tags.items():
                    if not isinstance(tag, dict) or "time" not in tag:
                        kept[tag_key] = tag
                        continue
                    original = tag["time"]
                    try:
                        original_f = float(original)
                    except (TypeError, ValueError):
                        kept[tag_key] = tag
                        continue
                    snapped = round(
                        round(original_f / _V4_SNAP_GRANULARITY) * _V4_SNAP_GRANULARITY,
                        6,
                    )
                    if snapped in seen:
                        existing_time = seen[snapped]
                        logger.warning(
                            "v3→v4 migration dropped colliding tag: "
                            "master_id=%s slave_id=%s tag_type=%s "
                            "original_time=%s snapped_time=%s "
                            "existing_time=%s",
                            master_id,
                            slave_id,
                            tag_type_name,
                            original,
                            snapped,
                            existing_time,
                        )
                        continue
                    tag["time"] = snapped
                    seen[snapped] = snapped
                    kept[tag_key] = tag
                tag_type["tags"] = kept
    envelope["schema_version"] = 4
    return envelope


def migrate_to_current(data: Any) -> Dict[str, Any]:
    """Apply migrations until data reaches CURRENT_SCHEMA_VERSION.

    Migration chain:
      - v0 (dict without schema_version): wrap in a v1 envelope,
        then chain v1→v2 → v2→v3 → v3→v4.
      - v1: chain v1→v2 → v2→v3 → v3→v4.
      - v2: chain v2→v3 → v3→v4.
      - v3: chain v3→v4 (snap tag times to 0.02s grid).
      - v4 (current): returned as-is.

    If `data` carries a version higher than CURRENT_SCHEMA_VERSION,
    SchemaValidationError is raised (prevent older code from
    silently corrupting newer files).
    """
    if not isinstance(data, dict):
        raise SchemaValidationError(
            f"top-level: expected dict, got {type(data).__name__}"
        )
    if "schema_version" not in data:
        envelope: Dict[str, Any] = {
            "schema_version": 1,
            "masters": data,
        }
        _coerce_legacy_tag_actions(envelope)
        _migrate_v1_to_v2(envelope)
        _migrate_v2_to_v3(envelope)
        _migrate_v3_to_v4(envelope)
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
    if version == 1:
        _coerce_legacy_tag_actions(data)
        _migrate_v1_to_v2(data)
        _migrate_v2_to_v3(data)
        _migrate_v3_to_v4(data)
        return data
    if version == 2:
        _coerce_legacy_tag_actions(data)
        _migrate_v2_to_v3(data)
        _migrate_v3_to_v4(data)
        return data
    if version == 3:
        _coerce_legacy_tag_actions(data)
        _migrate_v3_to_v4(data)
        return data
    if version == CURRENT_SCHEMA_VERSION:
        _coerce_legacy_tag_actions(data)
        return data
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
    """Validate that `data` is a well-formed current-schema envelope.

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
    """Read `path`, migrate, validate, return the current envelope.

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
