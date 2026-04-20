"""Helpers for duplicating Master and Slave subtrees into
CompositeCommand sequences. Pure application layer — builds
commands, does not execute them. Consumers push the returned
composite onto CommandStack.

Deep copy semantics go through json_mapper so no references
are shared between source and duplicate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Iterable, List, Optional

from lightconductor.application.commands import (
    AddMasterCommand,
    AddSlaveCommand,
    AddTagCommand,
    AddTagTypeCommand,
    Command,
    CompositeCommand,
)
from lightconductor.domain.models import Master, Slave, TagType
from lightconductor.infrastructure.json_mapper import (
    pack_master,
    pack_slave,
    unpack_master,
    unpack_slave,
)


def _default_id_factory() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S%f")


def resolve_copy_name(
    base_name: str,
    existing_names: Iterable[str],
) -> str:
    """Return "<base> (copy)" when unique, else "<base> (copy N)"
    for N = 2, 3, ... First collision-free candidate wins."""
    names = set(existing_names or [])
    candidate = f"{base_name} (copy)"
    if candidate not in names:
        return candidate
    n = 2
    while True:
        candidate = f"{base_name} (copy {n})"
        if candidate not in names:
            return candidate
        n += 1


def deep_copy_master(source: Master) -> Master:
    """Produce a deep-copied Master via json_mapper round trip.
    Source is not mutated; returned object shares no references
    with source."""
    packed = pack_master(source)
    return unpack_master(packed)


def deep_copy_slave(source: Slave) -> Slave:
    """Produce a deep-copied Slave via json_mapper round trip.
    Source is not mutated; returned object shares no references
    with source."""
    packed = pack_slave(source)
    return unpack_slave(packed)


def build_duplicate_master_composite(
    source: Master,
    existing_master_names: Iterable[str],
    id_factory: Optional[Callable[[], str]] = None,
) -> CompositeCommand:
    """Construct a CompositeCommand that duplicates a Master
    and its entire subtree (slaves, tag types, tags).

    The composite's children, in order:
      1. AddMasterCommand(new_master: Master with no slaves)
      2. For each source slave:
           AddSlaveCommand(master_id=new_master.id,
                           slave=copied slave without tag_types)
           For each tag_type in the copied slave:
               AddTagTypeCommand(master_id=new_master.id,
                                 slave_id=new_slave.id,
                                 tag_type=tag_type with empty tags)
               For each tag in that tag_type:
                   AddTagCommand(master_id=new_master.id,
                                 slave_id=new_slave.id,
                                 type_name=tag_type.name,
                                 tag=deep-copied tag)

    The top-level Master/Slave objects handed to AddMaster and
    AddSlave must carry empty slaves / empty tag_types
    respectively — their children arrive via subsequent
    AddSlave / AddTagType children of the composite. This
    mirrors how real user flows populate state."""
    make_id = id_factory or _default_id_factory
    dup_master = deep_copy_master(source)
    dup_master.id = make_id()
    dup_master.name = resolve_copy_name(
        source.name,
        existing_master_names,
    )
    slaves_in_order = list(dup_master.slaves.values())
    dup_master.slaves = {}

    children: List[Command] = [AddMasterCommand(master=dup_master)]

    seen_slave_names: set[str] = set()
    for src_slave in slaves_in_order:
        new_slave_id = make_id()
        new_slave_name = (
            resolve_copy_name(
                src_slave.name,
                seen_slave_names,
            )
            if src_slave.name in seen_slave_names
            else src_slave.name
        )
        seen_slave_names.add(new_slave_name)
        slave_shell = Slave(
            id=new_slave_id,
            name=new_slave_name,
            pin=src_slave.pin,
            led_count=src_slave.led_count,
            tag_types={},
        )
        children.append(
            AddSlaveCommand(
                master_id=dup_master.id,
                slave=slave_shell,
            )
        )
        for _type_name, tag_type in src_slave.tag_types.items():
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
                    master_id=dup_master.id,
                    slave_id=new_slave_id,
                    tag_type=tag_type_shell,
                )
            )
            for tag in tag_type.tags:
                children.append(
                    AddTagCommand(
                        master_id=dup_master.id,
                        slave_id=new_slave_id,
                        type_name=tag_type.name,
                        tag=tag,
                    )
                )
    return CompositeCommand(children=children)


def build_duplicate_slave_composite(
    source: Slave,
    target_master_id: str,
    existing_slave_names: Iterable[str],
    id_factory: Optional[Callable[[], str]] = None,
) -> CompositeCommand:
    """Construct a CompositeCommand that duplicates a Slave
    (and all its tag_types and tags) as a sibling under
    target_master_id.

    Children order: AddSlaveCommand, AddTagTypeCommand*,
    AddTagCommand*. Mirrors the slave-level portion of
    build_duplicate_master_composite."""
    make_id = id_factory or _default_id_factory
    dup_slave = deep_copy_slave(source)
    dup_slave.id = make_id()
    dup_slave.name = resolve_copy_name(
        source.name,
        existing_slave_names,
    )
    tag_types_copy = list(dup_slave.tag_types.items())
    dup_slave.tag_types = {}

    children: List[Command] = [
        AddSlaveCommand(
            master_id=target_master_id,
            slave=dup_slave,
        )
    ]
    for _type_name, tag_type in tag_types_copy:
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
                slave_id=dup_slave.id,
                tag_type=tag_type_shell,
            )
        )
        for tag in tag_type.tags:
            children.append(
                AddTagCommand(
                    master_id=target_master_id,
                    slave_id=dup_slave.id,
                    type_name=tag_type.name,
                    tag=tag,
                )
            )
    return CompositeCommand(children=children)
