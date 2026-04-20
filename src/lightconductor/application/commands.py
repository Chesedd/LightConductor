"""Command pattern for reversible project-state mutations.

Commands are plain-Python classes that mutate a ``ProjectState`` via
its public methods. Each command captures inverse-operation payload
on ``execute()`` and reverses it on ``undo()``. A ``CommandStack``
drives classical undo/redo semantics (push clears redo).

Commands are state-only: they do not touch widgets, do not import
Qt, and do not emit signals beyond those ``ProjectState`` already
emits on mutation. UI wiring (Ctrl+Z/Ctrl+Shift+Z, scene refresh on
execute/undo) is a later phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Iterable, List, Optional, Protocol, Union

from lightconductor.application.project_state import ProjectState
from lightconductor.domain.models import Master, Slave, Tag, TagType


class TopologyCollisionError(Exception):
    """Raised when AddTagTypeCommand detects topology cells
    overlapping with sibling TagTypes on the same slave. UI
    filtering in TopologyDialog prevents this normally; this is a
    belt-and-suspenders backstop for direct state mutations."""

    def __init__(
        self,
        master_id: str,
        slave_id: str,
        type_name: str,
        colliding_cells: Iterable[int],
    ) -> None:
        self.master_id = master_id
        self.slave_id = slave_id
        self.type_name = type_name
        self.colliding_cells: FrozenSet[int] = frozenset(colliding_cells)
        super().__init__(
            f"TagType {type_name!r} topology collides with sibling types "
            f"on slave {slave_id}: cells {sorted(self.colliding_cells)}"
        )


class Command(Protocol):
    """A reversible state mutation.

    `execute(state)` applies the mutation. `undo(state)` reverses
    it. Commands capture inverse-operation payload during
    `execute()` and store it on the instance. Calling `execute()`
    a second time after `undo()` replays the same mutation ("redo");
    calling `undo()` after `execute()` reverses the latest execute.
    """

    def execute(self, state: ProjectState) -> None: ...

    def undo(self, state: ProjectState) -> None: ...


@dataclass(slots=True)
class AddTagCommand:
    master_id: str
    slave_id: str
    type_name: str
    tag: Tag
    _applied_index: Optional[int] = field(default=None, init=False)

    def execute(self, state: ProjectState) -> None:
        self._applied_index = state.add_tag(
            self.master_id,
            self.slave_id,
            self.type_name,
            self.tag,
        )

    def undo(self, state: ProjectState) -> None:
        if self._applied_index is None:
            raise RuntimeError("undo called before execute")
        state.remove_tag(
            self.master_id,
            self.slave_id,
            self.type_name,
            self._applied_index,
        )
        self._applied_index = None


@dataclass(slots=True)
class DeleteTagCommand:
    master_id: str
    slave_id: str
    type_name: str
    tag_index: int
    _deleted_tag: Optional[Tag] = field(default=None, init=False)

    def execute(self, state: ProjectState) -> None:
        tags = (
            state.master(self.master_id)
            .slaves[self.slave_id]
            .tag_types[self.type_name]
            .tags
        )
        if self.tag_index < 0 or self.tag_index >= len(tags):
            raise IndexError(self.tag_index)
        self._deleted_tag = tags[self.tag_index]
        state.remove_tag(
            self.master_id,
            self.slave_id,
            self.type_name,
            self.tag_index,
        )

    def undo(self, state: ProjectState) -> None:
        if self._deleted_tag is None:
            raise RuntimeError("undo called before execute")
        # Reinsert the exact same Tag object (identity preserved).
        # state.add_tag bisect-inserts by time_seconds; the
        # resulting position will equal self.tag_index IFF no
        # other tags were added/removed at or before that position
        # between execute and undo. In practice the command stack
        # guarantees FIFO reversal, so position holds.
        state.add_tag(
            self.master_id,
            self.slave_id,
            self.type_name,
            self._deleted_tag,
        )
        self._deleted_tag = None


@dataclass(slots=True)
class MoveTagCommand:
    master_id: str
    slave_id: str
    type_name: str
    tag_index: int
    new_time_seconds: float
    tag_identity: Optional[int] = None
    _old_time_seconds: Optional[float] = field(default=None, init=False)
    _tag_ref: Optional[Tag] = field(default=None, init=False)

    def execute(self, state: ProjectState) -> None:
        tags = (
            state.master(self.master_id)
            .slaves[self.slave_id]
            .tag_types[self.type_name]
            .tags
        )
        resolved_index: Optional[int] = None
        if self.tag_identity is not None:
            for i, t in enumerate(tags):
                if id(t) == self.tag_identity:
                    resolved_index = i
                    break
            if resolved_index is None:
                raise IndexError(
                    f"tag_identity {self.tag_identity} not found in "
                    f"{self.master_id}/{self.slave_id}/{self.type_name}"
                )
        else:
            if self.tag_index < 0 or self.tag_index >= len(tags):
                raise IndexError(self.tag_index)
            resolved_index = self.tag_index
        self._tag_ref = tags[resolved_index]
        self._old_time_seconds = self._tag_ref.time_seconds
        # state.update_tag repositions the tag via pop+bisect-
        # reinsert when time_seconds changes. The _tag_ref
        # identity is preserved across the reposition.
        state.update_tag(
            self.master_id,
            self.slave_id,
            self.type_name,
            resolved_index,
            time_seconds=self.new_time_seconds,
        )

    def undo(self, state: ProjectState) -> None:
        if self._tag_ref is None or self._old_time_seconds is None:
            raise RuntimeError("undo called before execute")
        tags = (
            state.master(self.master_id)
            .slaves[self.slave_id]
            .tag_types[self.type_name]
            .tags
        )
        # Find the tag by identity (its post-execute position may
        # differ from self.tag_index due to repositioning).
        current_index = None
        for i, t in enumerate(tags):
            if t is self._tag_ref:
                current_index = i
                break
        if current_index is None:
            raise RuntimeError("tag not found during undo")
        state.update_tag(
            self.master_id,
            self.slave_id,
            self.type_name,
            current_index,
            time_seconds=self._old_time_seconds,
        )
        self._tag_ref = None
        self._old_time_seconds = None


@dataclass(slots=True)
class EditRangeCommand:
    master_id: str
    slave_id: str
    type_name: str
    new_pin: Optional[str] = None
    new_color: Union[List[int], str, None] = None  # per domain Model
    _old_pin: Optional[str] = field(default=None, init=False)
    _old_color: Union[List[int], str, None] = field(default=None, init=False)
    _captured: bool = field(default=False, init=False)

    def execute(self, state: ProjectState) -> None:
        tag_type = (
            state.master(self.master_id).slaves[self.slave_id].tag_types[self.type_name]
        )
        self._old_pin = tag_type.pin
        self._old_color = tag_type.color
        self._captured = True
        state.update_tag_type(
            self.master_id,
            self.slave_id,
            self.type_name,
            pin=self.new_pin,
            color=self.new_color,
        )

    def undo(self, state: ProjectState) -> None:
        if not self._captured:
            raise RuntimeError("undo called before execute")
        state.update_tag_type(
            self.master_id,
            self.slave_id,
            self.type_name,
            pin=self._old_pin,
            color=self._old_color,
        )
        self._captured = False
        self._old_pin = None
        self._old_color = None


@dataclass(slots=True)
class AddMasterCommand:
    master: Master

    def execute(self, state: ProjectState) -> None:
        state.add_master(self.master)

    def undo(self, state: ProjectState) -> None:
        state.remove_master(self.master.id)


@dataclass(slots=True)
class AddSlaveCommand:
    master_id: str
    slave: Slave

    def execute(self, state: ProjectState) -> None:
        state.add_slave(self.master_id, self.slave)

    def undo(self, state: ProjectState) -> None:
        state.remove_slave(self.master_id, self.slave.id)


@dataclass(slots=True)
class DeleteSlaveCommand:
    master_id: str
    slave_id: str
    _deleted_slave: Optional[Slave] = field(default=None, init=False)

    def execute(self, state: ProjectState) -> None:
        slave = state.master(self.master_id).slaves[self.slave_id]
        self._deleted_slave = slave
        state.remove_slave(self.master_id, self.slave_id)

    def undo(self, state: ProjectState) -> None:
        if self._deleted_slave is None:
            raise RuntimeError("undo called before execute")
        state.add_slave(self.master_id, self._deleted_slave)
        self._deleted_slave = None


@dataclass(slots=True)
class AddTagTypeCommand:
    master_id: str
    slave_id: str
    tag_type: TagType

    def execute(self, state: ProjectState) -> None:
        slave = state.master(self.master_id).slaves[self.slave_id]
        new_cells = {int(c) for c in (self.tag_type.topology or [])}
        occupied: set[int] = set()
        for sibling_name, sibling_tt in slave.tag_types.items():
            if sibling_name == self.tag_type.name:
                continue
            occupied.update(int(c) for c in (sibling_tt.topology or []))
        collisions = new_cells & occupied
        if collisions:
            raise TopologyCollisionError(
                master_id=self.master_id,
                slave_id=self.slave_id,
                type_name=self.tag_type.name,
                colliding_cells=collisions,
            )
        state.add_tag_type(self.master_id, self.slave_id, self.tag_type)

    def undo(self, state: ProjectState) -> None:
        state.remove_tag_type(
            self.master_id,
            self.slave_id,
            self.tag_type.name,
        )


@dataclass(slots=True)
class DeleteTagTypeCommand:
    master_id: str
    slave_id: str
    type_name: str
    _deleted_tag_type: Optional[TagType] = field(default=None, init=False)

    def execute(self, state: ProjectState) -> None:
        tt = (
            state.master(self.master_id).slaves[self.slave_id].tag_types[self.type_name]
        )
        self._deleted_tag_type = tt
        state.remove_tag_type(self.master_id, self.slave_id, self.type_name)

    def undo(self, state: ProjectState) -> None:
        if self._deleted_tag_type is None:
            raise RuntimeError("undo called before execute")
        state.add_tag_type(
            self.master_id,
            self.slave_id,
            self._deleted_tag_type,
        )
        self._deleted_tag_type = None


@dataclass(slots=True)
class EditTagCommand:
    master_id: str
    slave_id: str
    type_name: str
    tag_index: int
    new_time_seconds: Optional[float] = None
    new_action: Optional[bool] = None
    new_colors: Optional[List[List[int]]] = None
    _tag_ref: Optional[Tag] = field(default=None, init=False)
    _old_time_seconds: Optional[float] = field(default=None, init=False)
    _old_action: Optional[bool | str] = field(default=None, init=False)
    _old_colors: Optional[List[List[int]]] = field(default=None, init=False)
    _captured: bool = field(default=False, init=False)

    def execute(self, state: ProjectState) -> None:
        tags = (
            state.master(self.master_id)
            .slaves[self.slave_id]
            .tag_types[self.type_name]
            .tags
        )
        if self.tag_index < 0 or self.tag_index >= len(tags):
            raise IndexError(self.tag_index)
        self._tag_ref = tags[self.tag_index]
        self._old_time_seconds = self._tag_ref.time_seconds
        self._old_action = self._tag_ref.action
        self._old_colors = (
            list(self._tag_ref.colors) if self._tag_ref.colors is not None else None
        )
        self._captured = True
        state.update_tag(
            self.master_id,
            self.slave_id,
            self.type_name,
            self.tag_index,
            time_seconds=self.new_time_seconds,
            action=self.new_action,
            colors=self.new_colors,
        )

    def undo(self, state: ProjectState) -> None:
        if not self._captured:
            raise RuntimeError("undo called before execute")
        tags = (
            state.master(self.master_id)
            .slaves[self.slave_id]
            .tag_types[self.type_name]
            .tags
        )
        current_index = None
        for i, t in enumerate(tags):
            if t is self._tag_ref:
                current_index = i
                break
        if current_index is None:
            raise RuntimeError("tag not found during undo")
        state.update_tag(
            self.master_id,
            self.slave_id,
            self.type_name,
            current_index,
            time_seconds=self._old_time_seconds,
            action=self._old_action,
            colors=self._old_colors,
        )
        self._captured = False
        self._tag_ref = None
        self._old_time_seconds = None
        self._old_action = None
        self._old_colors = None


@dataclass(slots=True)
class CompositeCommand:
    """Composite of child commands. Executes children in
    order; undoes them in reverse. Atomic on failure:
    if a child's execute() raises, prior children are
    undone in reverse and the exception is re-raised.

    Intended for bulk user actions (bulk-delete,
    bulk-move) where one Ctrl+Z should revert the whole
    group in one step.
    """

    children: List[Command] = field(default_factory=list)
    _last_executed: int = field(default=-1, init=False)

    def execute(self, state: ProjectState) -> None:
        for i, child in enumerate(self.children):
            try:
                child.execute(state)
            except Exception:
                # Roll back everything we already applied.
                for j in range(i - 1, -1, -1):
                    try:
                        self.children[j].undo(state)
                    except Exception:
                        # Best-effort rollback; swallow to
                        # avoid masking the original error.
                        pass
                self._last_executed = -1
                raise
        self._last_executed = len(self.children) - 1

    def undo(self, state: ProjectState) -> None:
        if self._last_executed < 0:
            # No successful execute has happened; either the
            # command was never executed or the last execute
            # failed and rolled back. Either way: no-op.
            return
        for i in range(self._last_executed, -1, -1):
            self.children[i].undo(state)
        self._last_executed = -1


class CommandStack:
    """Undo/redo stack. Unbounded history."""

    def __init__(self, state: ProjectState) -> None:
        self._state = state
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []

    def push(self, command: Command) -> None:
        """Execute the command and push it onto the undo stack.
        Clears the redo stack (classical semantics)."""
        command.execute(self._state)
        self._undo_stack.append(command)
        self._redo_stack.clear()

    def undo(self) -> None:
        """Undo the most recent command. No-op if stack empty."""
        if not self._undo_stack:
            return
        command = self._undo_stack.pop()
        command.undo(self._state)
        self._redo_stack.append(command)

    def redo(self) -> None:
        """Re-execute the most recently undone command. No-op if
        redo stack empty."""
        if not self._redo_stack:
            return
        command = self._redo_stack.pop()
        command.execute(self._state)
        self._undo_stack.append(command)

    def clear(self) -> None:
        """Drop both stacks. Does NOT mutate state."""
        self._undo_stack.clear()
        self._redo_stack.clear()

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)
