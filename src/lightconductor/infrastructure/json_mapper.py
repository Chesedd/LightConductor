"""JSON serialization mapper between domain objects and data.json format.

This module is the single source of truth for pack/unpack logic
between `lightconductor.domain.models` objects and the nested dict
structure stored in per-project data.json files.

Phase 1.1 implements Tag only. TagType / Slave / Master will be
added in subsequent PRs (1.2 - 1.4).

Functions pack_* receive a domain object and return a plain dict.
Functions unpack_* receive a plain dict and return a domain object.
Values are passed through without type normalization to preserve
exact JSON equality for round-trip tests.
"""
from __future__ import annotations

from typing import Any, Dict

from lightconductor.domain.models import Tag


_TAG_REQUIRED_FIELDS = ("time", "action", "colors")


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
