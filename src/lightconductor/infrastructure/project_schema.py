from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple, cast

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 5

AUDIO_OFFSET_MS_MIN = -2000
AUDIO_OFFSET_MS_MAX = 2000


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
    ("brightness", (int, float)),
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


def wrap_boxes(
    boxes: Dict[str, Any],
    audio_offset_ms: int = 0,
) -> Dict[str, Any]:
    """Wrap a masters dict in the current envelope. Used on write.

    `audio_offset_ms` (Phase 24.1) is persisted at the envelope root.
    Default 0 preserves byte-equivalent behavior for callers that have
    not adopted the offset slider.
    """
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "masters": boxes,
        "audio_offset_ms": int(audio_offset_ms),
    }


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
    """Inject `brightness=1.0` on every slave that lacks the field.

    Phase 18.1: per-slave brightness is now a domain field used as a
    multiplicative scaler on the palette at compile time. The wire
    format and slave firmware are unchanged. Default 1.0 preserves
    visual behavior for legacy projects. Bumps envelope schema_version
    to 4. Returns the mutated envelope.

    Idempotent: slaves that already carry a `brightness` value are
    left untouched, so the function doubles as a v4 field repair when
    invoked on an envelope already at schema_version 4 (see
    `migrate_to_current` for the defensive-repair branch).
    """
    masters = envelope.get("masters")
    if not isinstance(masters, dict):
        envelope["schema_version"] = 4
        return envelope
    migrated = 0
    for master in masters.values():
        if not isinstance(master, dict):
            continue
        slaves = master.get("slaves")
        if not isinstance(slaves, dict):
            continue
        for slave in slaves.values():
            if not isinstance(slave, dict):
                continue
            if "brightness" not in slave:
                slave["brightness"] = 1.0
                migrated += 1
    if migrated:
        logger.info("migrated %d slaves to schema v4 with default brightness", migrated)
    envelope["schema_version"] = 4
    return envelope


def _clamp_audio_offset_ms(value: Any) -> int:
    """Coerce-and-clamp `value` into the AUDIO_OFFSET_MS_* range.

    Non-int (or non-coercible) values are reset to 0 with a warning.
    Out-of-range values are clamped to the nearest bound with a
    warning. Returns the safe int.
    """
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        logger.warning(
            "audio_offset_ms had non-int value %r; resetting to 0", value
        )
        return 0
    if ivalue > AUDIO_OFFSET_MS_MAX:
        logger.warning(
            "audio_offset_ms %d exceeds max %d; clamping",
            ivalue,
            AUDIO_OFFSET_MS_MAX,
        )
        return AUDIO_OFFSET_MS_MAX
    if ivalue < AUDIO_OFFSET_MS_MIN:
        logger.warning(
            "audio_offset_ms %d below min %d; clamping",
            ivalue,
            AUDIO_OFFSET_MS_MIN,
        )
        return AUDIO_OFFSET_MS_MIN
    return ivalue


def _migrate_v4_to_v5(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Inject root-level `audio_offset_ms=0` if missing; clamp if present.

    Phase 24.1: per-project sub-second offset between the master Start
    signal and audio playback. Default 0 preserves visual/audio behavior
    for legacy projects. Out-of-range values are clamped (with warning)
    rather than rejected — keeps hand-edited JSON from killing load.
    Bumps envelope schema_version to 5. Returns the mutated envelope.

    Idempotent: envelopes already carrying a valid in-range
    `audio_offset_ms` are left untouched, so the function doubles as a
    v5 field repair when invoked on an envelope already at
    schema_version 5 (see `migrate_to_current` for the
    defensive-repair branch).
    """
    if "audio_offset_ms" not in envelope:
        envelope["audio_offset_ms"] = 0
    else:
        envelope["audio_offset_ms"] = _clamp_audio_offset_ms(
            envelope["audio_offset_ms"]
        )
    envelope["schema_version"] = 5
    return envelope


def migrate_to_current(data: Any) -> Dict[str, Any]:
    """Apply migrations until data reaches CURRENT_SCHEMA_VERSION.

    Migration chain:
      - v0 (dict without schema_version): wrap in a v1 envelope,
        then v1→v2 grid-field, v2→v3 led_cells, v3→v4 brightness,
        v4→v5 audio_offset_ms.
      - v1: apply v1→v2, v2→v3, v3→v4, v4→v5.
      - v2: apply v2→v3, v3→v4, v4→v5.
      - v3: apply v3→v4 brightness, v4→v5 audio_offset_ms.
      - v4: apply v4→v5 audio_offset_ms.
      - v5 (current): legacy-action coercion, then `_migrate_v3_to_v4`
        and `_migrate_v4_to_v5` are re-run as defensive idempotent
        repairs for files saved by buggy intermediate code that bumped
        `schema_version` without injecting the corresponding fields.

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
        _migrate_v4_to_v5(envelope)
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
        _migrate_v4_to_v5(data)
        return data
    if version == 2:
        _coerce_legacy_tag_actions(data)
        _migrate_v2_to_v3(data)
        _migrate_v3_to_v4(data)
        _migrate_v4_to_v5(data)
        return data
    if version == 3:
        _coerce_legacy_tag_actions(data)
        _migrate_v3_to_v4(data)
        _migrate_v4_to_v5(data)
        return data
    if version == 4:
        _coerce_legacy_tag_actions(data)
        _migrate_v3_to_v4(data)
        _migrate_v4_to_v5(data)
        return data
    if version == CURRENT_SCHEMA_VERSION:
        _coerce_legacy_tag_actions(data)
        _migrate_v3_to_v4(data)
        _migrate_v4_to_v5(data)
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

    if "audio_offset_ms" not in data:
        raise SchemaValidationError(
            "top-level: missing required field 'audio_offset_ms'"
        )
    audio_offset_ms = data["audio_offset_ms"]
    if not isinstance(audio_offset_ms, int) or isinstance(audio_offset_ms, bool):
        raise SchemaValidationError(
            f"audio_offset_ms: expected int, "
            f"got {type(audio_offset_ms).__name__}"
        )
    if audio_offset_ms < AUDIO_OFFSET_MS_MIN or audio_offset_ms > AUDIO_OFFSET_MS_MAX:
        raise SchemaValidationError(
            f"audio_offset_ms: expected in range "
            f"[{AUDIO_OFFSET_MS_MIN}, {AUDIO_OFFSET_MS_MAX}], "
            f"got {audio_offset_ms}"
        )

    for key in data:
        if key not in ("schema_version", "masters", "audio_offset_ms"):
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
