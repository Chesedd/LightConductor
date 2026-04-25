"""Observable project state store.

Holds the canonical in-memory project data (masters -> slaves -> tag types
-> tags) and notifies subscribed listeners via a plain callback observer
model. Events are frozen dataclasses carrying IDs only; listeners re-query
the store for current data. The store keeps REFERENCES to domain objects
(no deep copies) -- callers must mutate through the store's methods, or
events will not fire. The store is Qt-free and headless-testable; Qt
adapters live at the widget layer.
"""

from __future__ import annotations

import bisect
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Union

from lightconductor.domain.models import Master, Slave, Tag, TagType

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StateReplaced:
    pass


@dataclass(frozen=True, slots=True)
class MasterAdded:
    master_id: str


@dataclass(frozen=True, slots=True)
class MasterRemoved:
    master_id: str


@dataclass(frozen=True, slots=True)
class MasterUpdated:
    master_id: str


@dataclass(frozen=True, slots=True)
class SlaveAdded:
    master_id: str
    slave_id: str


@dataclass(frozen=True, slots=True)
class SlaveRemoved:
    master_id: str
    slave_id: str


@dataclass(frozen=True, slots=True)
class SlaveUpdated:
    master_id: str
    slave_id: str


@dataclass(frozen=True, slots=True)
class TagTypeAdded:
    master_id: str
    slave_id: str
    type_name: str


@dataclass(frozen=True, slots=True)
class TagTypeRemoved:
    master_id: str
    slave_id: str
    type_name: str


@dataclass(frozen=True, slots=True)
class TagAdded:
    master_id: str
    slave_id: str
    type_name: str
    tag_index: int


@dataclass(frozen=True, slots=True)
class TagRemoved:
    master_id: str
    slave_id: str
    type_name: str
    tag_index: int


@dataclass(frozen=True, slots=True)
class TagUpdated:
    master_id: str
    slave_id: str
    type_name: str
    tag_index: int


@dataclass(frozen=True, slots=True)
class TagTypeUpdated:
    master_id: str
    slave_id: str
    type_name: str


ProjectStateEvent = Union[
    StateReplaced,
    MasterAdded,
    MasterRemoved,
    MasterUpdated,
    SlaveAdded,
    SlaveRemoved,
    SlaveUpdated,
    TagTypeAdded,
    TagTypeRemoved,
    TagAdded,
    TagRemoved,
    TagUpdated,
    TagTypeUpdated,
]


class DuplicateSlavePinError(ValueError):
    """Raised by ``ProjectState.add_slave`` when the incoming slave's
    ``pin`` collides with an existing slave's ``pin`` under the same
    master. Enforcing this at mutation time (rather than only at
    save-time validation) lets ``CompositeCommand`` roll back atomically
    when the conflict is produced mid-composite — e.g. applying a
    device template whose slave pin matches one already present in the
    target master.

    Scope matches ``ValidationService._check_duplicate_slave_pins``:
    comparison is within the single target master, and the pin value
    is stringified (so empty / whitespace strings participate in
    uniqueness, to stay consistent with the validator)."""

    def __init__(
        self,
        master_id: str,
        pin: str,
        existing_slave_id: str,
        new_slave_id: str,
    ) -> None:
        self.master_id = master_id
        self.pin = pin
        self.existing_slave_id = existing_slave_id
        self.new_slave_id = new_slave_id
        super().__init__(
            f"Duplicate slave pin {pin!r} in master "
            f"{master_id!r}: already used by slave "
            f"{existing_slave_id!r} (attempted add: "
            f"{new_slave_id!r})"
        )


class ProjectState:
    def __init__(self) -> None:
        self._masters: Dict[str, Master] = {}
        self._listeners: List[Callable[[ProjectStateEvent], None]] = []

    def subscribe(
        self,
        listener: Callable[[ProjectStateEvent], None],
    ) -> Callable[[], None]:
        """Register listener; returns an idempotent unsubscribe callable."""
        self._listeners.append(listener)

        def _unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return _unsubscribe

    def load_masters(self, masters: Dict[str, Master]) -> None:
        """Replace the entire master map. Emits StateReplaced exactly once.
        Each tag_type.tags list is sorted by time_seconds to maintain the
        class invariant that tags are always time-ordered."""
        self._masters = dict(masters)
        for master in self._masters.values():
            for slave in master.slaves.values():
                for tag_type in slave.tag_types.values():
                    tag_type.tags.sort(key=lambda t: t.time_seconds)
        self._emit(StateReplaced())

    def masters(self) -> Dict[str, Master]:
        """Return a shallow copy of the internal master map."""
        return dict(self._masters)

    def has_master(self, master_id: str) -> bool:
        return master_id in self._masters

    def master(self, master_id: str) -> Master:
        """Raises KeyError if missing."""
        return self._masters[master_id]

    def add_master(self, master: Master) -> None:
        """Raises ValueError if master.id already present."""
        if master.id in self._masters:
            raise ValueError(f"master already present: {master.id!r}")
        self._masters[master.id] = master
        self._emit(MasterAdded(master_id=master.id))

    def remove_master(self, master_id: str) -> None:
        """Raises KeyError if missing."""
        if master_id not in self._masters:
            raise KeyError(master_id)
        del self._masters[master_id]
        self._emit(MasterRemoved(master_id=master_id))

    def update_master_ip(self, master_id: str, new_ip: str) -> None:
        """Set the master's IP and emit MasterUpdated. Emits even when
        ``new_ip`` equals the current value — matches the convention
        used by ``update_tag_type`` (always emit; consumers deduplicate
        if they care). Raises KeyError if the master is missing."""
        master = self._masters[master_id]
        master.ip = new_ip
        self._emit(MasterUpdated(master_id=master_id))

    def add_slave(self, master_id: str, slave: Slave) -> None:
        """Raises KeyError if master missing, ValueError on duplicate
        slave id, and ``DuplicateSlavePinError`` if another slave in
        the same master already uses ``slave.pin``. The pin check runs
        before mutation and before the event emission, so a failed add
        leaves no state change and fires no event."""
        master = self._masters[master_id]
        if slave.id in master.slaves:
            raise ValueError(f"slave already present: {slave.id!r}")
        new_pin_key = str(slave.pin)
        for existing_id, existing in master.slaves.items():
            if str(existing.pin) == new_pin_key:
                raise DuplicateSlavePinError(
                    master_id=master_id,
                    pin=new_pin_key,
                    existing_slave_id=existing_id,
                    new_slave_id=slave.id,
                )
        master.slaves[slave.id] = slave
        self._emit(SlaveAdded(master_id=master_id, slave_id=slave.id))

    def remove_slave(self, master_id: str, slave_id: str) -> None:
        """Raises KeyError if master or slave missing."""
        master = self._masters[master_id]
        if slave_id not in master.slaves:
            raise KeyError(slave_id)
        del master.slaves[slave_id]
        self._emit(SlaveRemoved(master_id=master_id, slave_id=slave_id))

    def update_slave_brightness(
        self,
        master_id: str,
        slave_id: str,
        new_brightness: float,
    ) -> None:
        """Set the slave's brightness and emit SlaveUpdated. Always emits
        — matches the convention used by ``update_master_ip``. Raises
        KeyError if the master or slave is missing. No range clamping
        here; ``compile_show`` clamps defensively at render time."""
        master = self._masters[master_id]
        slave = master.slaves[slave_id]
        slave.brightness = float(new_brightness)
        self._emit(SlaveUpdated(master_id=master_id, slave_id=slave_id))

    def add_tag_type(
        self,
        master_id: str,
        slave_id: str,
        tag_type: TagType,
    ) -> None:
        """Raises KeyError on missing master/slave, ValueError on duplicate name."""
        slave = self._masters[master_id].slaves[slave_id]
        if tag_type.name in slave.tag_types:
            raise ValueError(f"tag type already present: {tag_type.name!r}")
        slave.tag_types[tag_type.name] = tag_type
        self._emit(
            TagTypeAdded(
                master_id=master_id,
                slave_id=slave_id,
                type_name=tag_type.name,
            )
        )

    def remove_tag_type(
        self,
        master_id: str,
        slave_id: str,
        type_name: str,
    ) -> None:
        """Raises KeyError on any missing level."""
        slave = self._masters[master_id].slaves[slave_id]
        if type_name not in slave.tag_types:
            raise KeyError(type_name)
        del slave.tag_types[type_name]
        self._emit(
            TagTypeRemoved(
                master_id=master_id,
                slave_id=slave_id,
                type_name=type_name,
            )
        )

    def update_tag_type(
        self,
        master_id: str,
        slave_id: str,
        type_name: str,
        *,
        pin: Optional[str] = None,
        color: Union[List[int], str, None] = None,
    ) -> None:
        """Update display metadata on a TagType. Fields left as
        None are unchanged. Always emits TagTypeUpdated, even if
        no field changed. Raises KeyError on missing levels."""
        tag_type = self._masters[master_id].slaves[slave_id].tag_types[type_name]
        if pin is not None:
            tag_type.pin = pin
        if color is not None:
            tag_type.color = color
        self._emit(
            TagTypeUpdated(
                master_id=master_id,
                slave_id=slave_id,
                type_name=type_name,
            )
        )

    def add_tag(
        self,
        master_id: str,
        slave_id: str,
        type_name: str,
        tag: Tag,
    ) -> int:
        """Insert tag at bisect position by time_seconds; returns the
        insertion index. KeyError on missing levels."""
        tag_type = self._masters[master_id].slaves[slave_id].tag_types[type_name]
        tags = tag_type.tags
        new_index = bisect.bisect_left(
            [t.time_seconds for t in tags],
            tag.time_seconds,
        )
        tags.insert(new_index, tag)
        self._emit(
            TagAdded(
                master_id=master_id,
                slave_id=slave_id,
                type_name=type_name,
                tag_index=new_index,
            )
        )
        return new_index

    def remove_tag(
        self,
        master_id: str,
        slave_id: str,
        type_name: str,
        tag_index: int,
    ) -> None:
        """Remove tag at index. KeyError on missing levels, IndexError on
        out-of-range index. Emitted event carries the removed index."""
        tag_type = self._masters[master_id].slaves[slave_id].tag_types[type_name]
        if tag_index < 0 or tag_index >= len(tag_type.tags):
            raise IndexError(tag_index)
        del tag_type.tags[tag_index]
        self._emit(
            TagRemoved(
                master_id=master_id,
                slave_id=slave_id,
                type_name=type_name,
                tag_index=tag_index,
            )
        )

    def update_tag(
        self,
        master_id: str,
        slave_id: str,
        type_name: str,
        tag_index: int,
        *,
        time_seconds: float | None = None,
        action: bool | str | None = None,
        colors: List[List[int]] | None = None,
    ) -> None:
        """Update provided fields. If time_seconds changes, the tag is
        repositioned to keep tag_type.tags sorted by time. Always emits
        TagUpdated; emitted tag_index reflects the post-update position."""
        tag_type = self._masters[master_id].slaves[slave_id].tag_types[type_name]
        if tag_index < 0 or tag_index >= len(tag_type.tags):
            raise IndexError(tag_index)
        tag = tag_type.tags[tag_index]
        reposition = time_seconds is not None and time_seconds != tag.time_seconds
        if time_seconds is not None:
            tag.time_seconds = time_seconds
        if action is not None:
            tag.action = action
        if colors is not None:
            tag.colors = colors
        if reposition:
            del tag_type.tags[tag_index]
            new_index = bisect.bisect_left(
                [t.time_seconds for t in tag_type.tags],
                tag.time_seconds,
            )
            tag_type.tags.insert(new_index, tag)
        else:
            new_index = tag_index
        self._emit(
            TagUpdated(
                master_id=master_id,
                slave_id=slave_id,
                type_name=type_name,
                tag_index=new_index,
            )
        )

    def _emit(self, event: ProjectStateEvent) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                logger.warning(
                    "listener raised while handling %s",
                    type(event).__name__,
                    exc_info=True,
                )
