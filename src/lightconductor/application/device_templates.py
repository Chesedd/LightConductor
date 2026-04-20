"""Pure helpers for device templates — a global, tagless library of
slave configurations. Consumed by ProjectWindow (save), MasterBox
(apply). No Qt, no settings persistence (caller owns that).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from lightconductor.application.commands import (
    AddSlaveCommand,
    AddTagTypeCommand,
    Command,
    CompositeCommand,
)
from lightconductor.domain.models import Slave, TagType
from lightconductor.infrastructure.json_mapper import (
    pack_slave,
    unpack_slave,
)

TEMPLATE_CURRENT_VERSION = 1


def _default_template_id_factory() -> str:
    return "tpl-" + datetime.now().strftime("%Y%m%d%H%M%S%f")


def template_from_slave(
    slave: Slave,
    template_name: str,
    template_id_factory: Optional[Callable[[], str]] = None,
) -> Dict[str, Any]:
    """Build a template dict from a domain Slave. Strips all tags
    (template_version=1). Pure; does not mutate the source slave."""
    make_id = template_id_factory or _default_template_id_factory
    packed = pack_slave(slave)
    stripped_tag_types = {}
    for type_name, tt in packed.get("tagTypes", {}).items():
        tt_copy = dict(tt)
        tt_copy["tags"] = {}
        stripped_tag_types[type_name] = tt_copy
    slave_config = {
        "name": packed["name"],
        "pin": packed["pin"],
        "led_count": packed["led_count"],
        "grid_rows": packed["grid_rows"],
        "grid_columns": packed["grid_columns"],
        "id": packed["id"],
        "tagTypes": stripped_tag_types,
    }
    return {
        "template_version": TEMPLATE_CURRENT_VERSION,
        "template_id": make_id(),
        "template_name": template_name or "",
        "slave_config": slave_config,
    }


def slave_from_template(
    template: Dict[str, Any],
    new_slave_id: str,
    new_slave_name: Optional[str] = None,
) -> Slave:
    """Construct a domain Slave from a template dict. The returned
    slave has tag_types from the template (also with fresh objects)
    but no tags. new_slave_id replaces the id field so multiple
    applications of the same template produce distinct slaves.
    new_slave_name when provided overrides the template's stored
    name; when None, the template name is kept."""
    if not isinstance(template, dict):
        raise ValueError("template: expected dict")
    slave_config = template.get("slave_config")
    if not isinstance(slave_config, dict):
        raise ValueError("template.slave_config: expected dict")
    slave_config_copy = dict(slave_config)
    slave_config_copy["id"] = new_slave_id
    if new_slave_name is not None:
        slave_config_copy["name"] = new_slave_name
    tag_types_copy = {}
    for type_name, tt in slave_config.get("tagTypes", {}).items():
        if not isinstance(tt, dict):
            raise ValueError(
                f"template.slave_config.tagTypes.{type_name}: expected dict",
            )
        tt_copy = dict(tt)
        tt_copy["tags"] = {}
        tag_types_copy[type_name] = tt_copy
    slave_config_copy["tagTypes"] = tag_types_copy
    return unpack_slave(slave_config_copy)


def build_apply_template_composite(
    template: Dict[str, Any],
    target_master_id: str,
    new_slave_id: str,
    new_slave_name: Optional[str] = None,
) -> CompositeCommand:
    """Construct a CompositeCommand that creates a new slave from the
    template under target_master_id. Children:
      1. AddSlaveCommand with empty tag_types.
      2. AddTagTypeCommand per tag_type in the template (all with
         empty tags).
    No AddTagCommand children — templates carry no tags."""
    full = slave_from_template(
        template,
        new_slave_id,
        new_slave_name,
    )
    tag_types_in_order = list(full.tag_types.items())
    slave_shell = Slave(
        id=full.id,
        name=full.name,
        pin=full.pin,
        led_count=full.led_count,
        grid_rows=full.grid_rows,
        grid_columns=full.grid_columns,
        tag_types={},
    )
    children: List[Command] = [
        AddSlaveCommand(
            master_id=target_master_id,
            slave=slave_shell,
        )
    ]
    for _type_name, tag_type in tag_types_in_order:
        tag_type_shell = TagType(
            name=tag_type.name,
            pin=tag_type.pin,
            rows=tag_type.rows,
            columns=tag_type.columns,
            color=tag_type.color,
            topology=list(tag_type.topology),
            tags=[],
        )
        children.append(
            AddTagTypeCommand(
                master_id=target_master_id,
                slave_id=full.id,
                tag_type=tag_type_shell,
            )
        )
    return CompositeCommand(children=children)
