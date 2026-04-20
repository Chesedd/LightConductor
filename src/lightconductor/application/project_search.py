"""Pure search and filter helpers for the project tree. Decides
which Master / Slave / TagType nodes should be visible for a given
query. No Qt, no widgets. Callers walk their widget trees and apply
the results via setVisible."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from lightconductor.domain.models import Master


@dataclass(slots=True, frozen=True)
class SlaveVisibility:
    visible: bool
    tag_types: Dict[str, bool] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class MasterVisibility:
    visible: bool
    slaves: Dict[str, SlaveVisibility] = field(default_factory=dict)


def _match(query_normalized: str, name: str) -> bool:
    """Case-insensitive substring match. Empty query always matches."""
    if not query_normalized:
        return True
    if not isinstance(name, str):
        return False
    return query_normalized in name.lower()


def compute_visibility(
    masters: Dict[str, Master],
    query: str,
) -> Dict[str, MasterVisibility]:
    """Return visibility decisions for every node in the project tree.

    Keys of the returned dict mirror ``masters`` keys. Each
    MasterVisibility contains per-slave entries (again by id); each
    SlaveVisibility carries per-tag-type booleans.

    Cascade: a TagType is visible iff its name matches the query. A
    Slave is visible iff its name matches OR any of its tag types is
    visible. A Master is visible iff its name matches OR any of its
    slaves is visible.

    Empty query -> everything visible.
    """
    q = (query or "").strip().lower()
    result: Dict[str, MasterVisibility] = {}
    for master_id, master in (masters or {}).items():
        master_matches = _match(q, getattr(master, "name", ""))
        slave_visibilities: Dict[str, SlaveVisibility] = {}
        any_slave_visible = False
        for slave_id, slave in (master.slaves or {}).items():
            slave_matches = _match(q, getattr(slave, "name", ""))
            tag_type_visibilities: Dict[str, bool] = {}
            any_type_visible = False
            for type_name in slave.tag_types or {}:
                tt_visible = _match(q, type_name)
                tag_type_visibilities[type_name] = tt_visible
                if tt_visible:
                    any_type_visible = True
            slave_visible = slave_matches or any_type_visible
            slave_visibilities[slave_id] = SlaveVisibility(
                visible=slave_visible,
                tag_types=tag_type_visibilities,
            )
            if slave_visible:
                any_slave_visible = True
        master_visible = master_matches or any_slave_visible
        result[master_id] = MasterVisibility(
            visible=master_visible,
            slaves=slave_visibilities,
        )
    return result
