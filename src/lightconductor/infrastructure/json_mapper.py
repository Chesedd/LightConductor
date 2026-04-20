"""JSON serialization mapper between domain objects and data.json format.

This module is the single source of truth for pack/unpack logic
between `lightconductor.domain.models` objects and the nested dict
structure stored in per-project data.json files.

Phase 1.1 implemented Tag. Phase 1.2 added TagType. Phase 1.3 added
Slave. Phase 1.4 adds Master — with this, Phase 1 roadmap point 1
(unified mapper) is complete. The unpack_* functions are fully
defined but not yet consumed in production; the next PR of Phase 1
(roadmap lines 49-51) will route project loading through them and
retire the Legacy*Storage / LegacyProjectsRepository shims.

Functions pack_* receive a domain object and return a plain dict.
Functions unpack_* receive a plain dict and return a domain object.
Values are passed through without type normalization to preserve
exact JSON equality for round-trip tests.
"""

from __future__ import annotations

from typing import Any, Dict

from lightconductor.domain.models import Master, Slave, Tag, TagType

_TAG_REQUIRED_FIELDS = ("time", "action", "colors")

_TAG_TYPE_REQUIRED_FIELDS = (
    "color",
    "pin",
    "row",
    "table",
    "topology",
    "tags",
)

_SLAVE_REQUIRED_FIELDS = (
    "name",
    "pin",
    "led_count",
    "grid_rows",
    "grid_columns",
    "id",
    "tagTypes",
)

_MASTER_REQUIRED_FIELDS = ("name", "id", "ip", "slaves")


def pack_tag(tag: Tag) -> Dict[str, Any]:
    """Serialize a domain Tag into the data.json dict shape."""
    return {
        "time": tag.time_seconds,
        "action": tag.action,
        "colors": tag.colors,
    }


def unpack_tag(data: Dict[str, Any]) -> Tag:
    """Deserialize a data.json tag dict into a domain Tag.

    Raises ValueError with a descriptive path-prefixed message if
    required fields are missing.
    """
    if not isinstance(data, dict):
        raise ValueError(f"tag: expected dict, got {type(data).__name__}")
    missing = [k for k in _TAG_REQUIRED_FIELDS if k not in data]
    if missing:
        raise ValueError(f"tag: missing required field(s): {missing}")
    return Tag(
        time_seconds=data["time"],
        action=data["action"],
        colors=data["colors"],
    )


def pack_tag_type(tag_type: TagType) -> Dict[str, Any]:
    """Serialize a domain TagType into the data.json dict shape.

    Note: `tag_type.name` is NOT included in the output dict — the
    name lives as a key in the enclosing `slave["tagTypes"]` dict
    and is handled one level up.

    `segment_start` and `segment_size` are derived fields (pin and
    len(topology) respectively) preserved for backward compatibility
    with existing data.json files.
    """
    return {
        "color": tag_type.color,
        "pin": tag_type.pin,
        "segment_start": tag_type.pin,
        "segment_size": len(tag_type.topology),
        "row": tag_type.rows,
        "table": tag_type.columns,
        "topology": tag_type.topology,
        "tags": {i: pack_tag(t) for i, t in enumerate(tag_type.tags)},
    }


def unpack_tag_type(data: Dict[str, Any], *, name: str) -> TagType:
    """Deserialize a data.json tag_type dict into a domain TagType.

    The `name` parameter is required because the TagType name is the
    key in the enclosing tagTypes dict, not part of `data`.

    `segment_start` and `segment_size` in `data` are ignored: they
    are derived from `pin` and `topology` respectively at pack time.

    The `tags` dict may use int or str keys (live dicts have int
    keys; json.load produces str keys). Keys are sorted numerically
    to recover the original tag order.
    """
    if not isinstance(data, dict):
        raise ValueError(f"tag_type: expected dict, got {type(data).__name__}")
    missing = [k for k in _TAG_TYPE_REQUIRED_FIELDS if k not in data]
    if missing:
        raise ValueError(f"tag_type: missing required field(s): {missing}")
    if not isinstance(data["tags"], dict):
        raise ValueError(
            f"tag_type.tags: expected dict, got {type(data['tags']).__name__}"
        )
    try:
        ordered_keys = sorted(data["tags"], key=lambda k: int(k))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"tag_type.tags: non-integer key in {list(data['tags'])}"
        ) from exc
    tags = [unpack_tag(data["tags"][k]) for k in ordered_keys]
    return TagType(
        name=name,
        pin=data["pin"],
        rows=data["row"],
        columns=data["table"],
        color=data["color"],
        topology=data["topology"],
        tags=tags,
    )


def pack_slave(slave: Slave) -> Dict[str, Any]:
    """Serialize a domain Slave into the data.json dict shape.

    `slave.tag_types` keys become `tagTypes` keys one-to-one; each
    value is recursively packed via pack_tag_type().
    """
    return {
        "name": slave.name,
        "pin": slave.pin,
        "led_count": slave.led_count,
        "grid_rows": slave.grid_rows,
        "grid_columns": slave.grid_columns,
        "id": slave.id,
        "tagTypes": {
            type_name: pack_tag_type(tt) for type_name, tt in slave.tag_types.items()
        },
    }


def unpack_slave(data: Dict[str, Any]) -> Slave:
    """Deserialize a data.json slave dict into a domain Slave.

    The `led_count` dataclass default (0) is only for in-code
    construction — here the JSON field is required.
    """
    if not isinstance(data, dict):
        raise ValueError(f"slave: expected dict, got {type(data).__name__}")
    missing = [k for k in _SLAVE_REQUIRED_FIELDS if k not in data]
    if missing:
        raise ValueError(f"slave: missing required field(s): {missing}")
    if not isinstance(data["tagTypes"], dict):
        raise ValueError(
            f"slave.tagTypes: expected dict, got {type(data['tagTypes']).__name__}"
        )
    tag_types = {
        type_name: unpack_tag_type(td, name=type_name)
        for type_name, td in data["tagTypes"].items()
    }
    return Slave(
        id=data["id"],
        name=data["name"],
        pin=data["pin"],
        led_count=data["led_count"],
        grid_rows=data["grid_rows"],
        grid_columns=data["grid_columns"],
        tag_types=tag_types,
    )


def pack_master(master: Master) -> Dict[str, Any]:
    """Serialize a domain Master into the data.json dict shape.

    `master.slaves` keys become `slaves` keys one-to-one; each
    value is recursively packed via pack_slave().
    """
    return {
        "name": master.name,
        "id": master.id,
        "ip": master.ip,
        "slaves": {slave_id: pack_slave(s) for slave_id, s in master.slaves.items()},
    }


def unpack_master(data: Dict[str, Any]) -> Master:
    """Deserialize a data.json master dict into a domain Master.

    All four fields (name, id, ip, slaves) are required. The
    `ip="192.168.0.129"` dataclass default is intentionally not
    applied here — that fallback lives on the UI->domain boundary in
    `ProjectManager.packMaster`, not in the mapper.
    """
    if not isinstance(data, dict):
        raise ValueError(f"master: expected dict, got {type(data).__name__}")
    missing = [k for k in _MASTER_REQUIRED_FIELDS if k not in data]
    if missing:
        raise ValueError(f"master: missing required field(s): {missing}")
    if not isinstance(data["slaves"], dict):
        raise ValueError(
            f"master.slaves: expected dict, got {type(data['slaves']).__name__}"
        )
    slaves = {slave_id: unpack_slave(sd) for slave_id, sd in data["slaves"].items()}
    return Master(
        id=data["id"],
        name=data["name"],
        ip=data["ip"],
        slaves=slaves,
    )
