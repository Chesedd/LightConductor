"""JSON serialization mapper between domain objects and data.json format.

This module is the single source of truth for pack/unpack logic
between `lightconductor.domain.models` objects and the nested dict
structure stored in per-project data.json files.

Phase 1.1 implemented Tag. Phase 1.2 adds TagType. Slave and Master
will be added in subsequent PRs (1.3 and 1.4).

Functions pack_* receive a domain object and return a plain dict.
Functions unpack_* receive a plain dict and return a domain object.
Values are passed through without type normalization to preserve
exact JSON equality for round-trip tests.
"""
from __future__ import annotations

from typing import Any, Dict

from lightconductor.domain.models import Tag, TagType


_TAG_REQUIRED_FIELDS = ("time", "action", "colors")

_TAG_TYPE_REQUIRED_FIELDS = (
    "color", "pin", "row", "table", "topology", "tags",
)


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
        raise ValueError(
            f"tag_type: expected dict, got {type(data).__name__}"
        )
    missing = [k for k in _TAG_TYPE_REQUIRED_FIELDS if k not in data]
    if missing:
        raise ValueError(f"tag_type: missing required field(s): {missing}")
    if not isinstance(data["tags"], dict):
        raise ValueError(
            f"tag_type.tags: expected dict, got "
            f"{type(data['tags']).__name__}"
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
