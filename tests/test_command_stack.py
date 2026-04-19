import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.commands import (
    AddMasterCommand,
    AddSlaveCommand,
    AddTagCommand,
    AddTagTypeCommand,
    CommandStack,
    DeleteSlaveCommand,
    DeleteTagCommand,
    DeleteTagTypeCommand,
    EditTagCommand,
    MoveTagCommand,
)
from lightconductor.application.project_state import ProjectState
from lightconductor.domain.models import Master, Slave, Tag, TagType


def _master(master_id="m1", name="Master 1"):
    return Master(id=master_id, name=name)


def _slave(slave_id="s1", name="Slave 1", pin="0"):
    return Slave(id=slave_id, name=name, pin=pin)


def _tag_type(name="tt1", pin="1", rows=1, columns=1):
    return TagType(name=name, pin=pin, rows=rows, columns=columns)


def _tag(time_seconds=0.0, action=True, colors=None):
    return Tag(
        time_seconds=time_seconds,
        action=action,
        colors=list(colors) if colors is not None else [],
    )


@pytest.fixture
def state():
    s = ProjectState()
    s.add_master(_master("m1"))
    s.add_slave("m1", _slave("s1"))
    s.add_tag_type("m1", "s1", _tag_type("tt1"))
    return s


@pytest.fixture
def stack(state):
    return CommandStack(state)


def _tags(state):
    return state.master("m1").slaves["s1"].tag_types["tt1"].tags


# ---------------------------------------------------------------------------
# Basic stack behavior
# ---------------------------------------------------------------------------

def test_new_stack_has_no_undo_no_redo(stack):
    assert stack.can_undo() is False
    assert stack.can_redo() is False


def test_push_executes_and_enables_undo(state, stack):
    cmd = AddTagCommand("m1", "s1", "tt1", _tag(time_seconds=1.0))

    stack.push(cmd)

    assert [t.time_seconds for t in _tags(state)] == [1.0]
    assert stack.can_undo() is True
    assert stack.can_redo() is False


def test_undo_reverses_and_enables_redo(state, stack):
    stack.push(AddTagCommand("m1", "s1", "tt1", _tag(time_seconds=1.0)))

    stack.undo()

    assert _tags(state) == []
    assert stack.can_undo() is False
    assert stack.can_redo() is True


def test_redo_replays_and_disables_redo(state, stack):
    stack.push(AddTagCommand("m1", "s1", "tt1", _tag(time_seconds=1.0)))
    stack.undo()

    stack.redo()

    assert [t.time_seconds for t in _tags(state)] == [1.0]
    assert stack.can_undo() is True
    assert stack.can_redo() is False


def test_new_push_clears_redo_stack(state, stack):
    stack.push(AddTagCommand("m1", "s1", "tt1", _tag(time_seconds=1.0)))
    stack.undo()
    assert stack.can_redo() is True

    stack.push(AddTagCommand("m1", "s1", "tt1", _tag(time_seconds=2.0)))

    assert stack.can_redo() is False
    # First command's tag stays removed; only the second command's tag is
    # present (redo path for the first command is gone).
    assert [t.time_seconds for t in _tags(state)] == [2.0]


def test_undo_on_empty_stack_is_noop(state, stack):
    stack.undo()  # must not raise

    assert stack.can_undo() is False
    assert stack.can_redo() is False
    assert _tags(state) == []


def test_redo_on_empty_stack_is_noop(state, stack):
    stack.redo()  # must not raise

    assert stack.can_undo() is False
    assert stack.can_redo() is False
    assert _tags(state) == []


def test_full_cycle_execute_undo_redo_execute_again(state, stack):
    tag_a = _tag(time_seconds=1.0)
    stack.push(AddTagCommand("m1", "s1", "tt1", tag_a))
    assert [t.time_seconds for t in _tags(state)] == [1.0]

    stack.undo()
    assert _tags(state) == []

    stack.redo()
    assert [t.time_seconds for t in _tags(state)] == [1.0]

    stack.push(MoveTagCommand("m1", "s1", "tt1", 0, new_time_seconds=2.5))
    assert [t.time_seconds for t in _tags(state)] == [2.5]

    stack.undo()
    assert [t.time_seconds for t in _tags(state)] == [1.0]

    stack.redo()
    assert [t.time_seconds for t in _tags(state)] == [2.5]

    assert len(stack._undo_stack) == 2
    assert len(stack._redo_stack) == 0


def test_clear_drops_both_stacks_but_keeps_state(state, stack):
    stack.push(AddTagCommand("m1", "s1", "tt1", _tag(time_seconds=1.0)))
    stack.push(MoveTagCommand("m1", "s1", "tt1", 0, new_time_seconds=2.5))
    assert [t.time_seconds for t in _tags(state)] == [2.5]

    stack.clear()

    assert stack.can_undo() is False
    assert stack.can_redo() is False
    assert [t.time_seconds for t in _tags(state)] == [2.5]


# ---------------------------------------------------------------------------
# Integration with the broader command set
# ---------------------------------------------------------------------------

def test_stack_add_master_undo_redo_cycle():
    s = ProjectState()
    stack = CommandStack(s)
    new_master = _master("m2", name="Master 2")

    stack.push(AddMasterCommand(new_master))
    assert s.has_master("m2")
    assert stack.can_undo() is True
    assert stack.can_redo() is False

    stack.undo()
    assert not s.has_master("m2")
    assert stack.can_undo() is False
    assert stack.can_redo() is True

    stack.redo()
    assert s.has_master("m2")
    assert s.master("m2") is new_master
    assert stack.can_undo() is True
    assert stack.can_redo() is False


def test_stack_add_master_then_add_slave_undo_in_reverse_order():
    s = ProjectState()
    stack = CommandStack(s)
    master = _master("m2", name="Master 2")
    slave = _slave("s9", pin="3")

    stack.push(AddMasterCommand(master))
    stack.push(AddSlaveCommand("m2", slave))
    assert "s9" in s.master("m2").slaves

    stack.undo()  # undo add-slave
    assert "s9" not in s.master("m2").slaves
    assert s.has_master("m2")

    stack.undo()  # undo add-master
    assert not s.has_master("m2")


def test_stack_delete_slave_undo_restores_identity(state, stack):
    original_slave = state.master("m1").slaves["s1"]

    stack.push(DeleteSlaveCommand("m1", "s1"))
    assert "s1" not in state.master("m1").slaves

    stack.undo()
    assert state.master("m1").slaves["s1"] is original_slave


def test_stack_add_tag_type_then_add_tag_chained_undo_redo(state, stack):
    new_tt = _tag_type(name="tt2", pin="5")
    stack.push(AddTagTypeCommand("m1", "s1", new_tt))
    new_tag = _tag(time_seconds=1.0)
    stack.push(AddTagCommand("m1", "s1", "tt2", new_tag))

    assert [t.time_seconds for t in state.master("m1").slaves["s1"].tag_types["tt2"].tags] == [1.0]

    stack.undo()  # undo add-tag
    assert state.master("m1").slaves["s1"].tag_types["tt2"].tags == []

    stack.undo()  # undo add-tag-type
    assert "tt2" not in state.master("m1").slaves["s1"].tag_types

    stack.redo()  # redo add-tag-type
    assert "tt2" in state.master("m1").slaves["s1"].tag_types
    assert state.master("m1").slaves["s1"].tag_types["tt2"] is new_tt

    stack.redo()  # redo add-tag
    tags = state.master("m1").slaves["s1"].tag_types["tt2"].tags
    assert [t.time_seconds for t in tags] == [1.0]


def test_stack_edit_tag_chain_with_add_full_cycle(state, stack):
    new_tag = _tag(time_seconds=1.0)
    stack.push(AddTagCommand("m1", "s1", "tt1", new_tag))
    assert [t.time_seconds for t in _tags(state)] == [1.0]

    stack.push(EditTagCommand(
        "m1", "s1", "tt1", tag_index=0, new_time_seconds=2.5,
    ))
    assert [t.time_seconds for t in _tags(state)] == [2.5]

    stack.undo()  # undo edit
    assert [t.time_seconds for t in _tags(state)] == [1.0]

    stack.redo()  # redo edit
    assert [t.time_seconds for t in _tags(state)] == [2.5]

    stack.undo()  # undo edit again
    stack.undo()  # undo add
    assert _tags(state) == []

    stack.redo()  # redo add
    stack.redo()  # redo edit
    assert [t.time_seconds for t in _tags(state)] == [2.5]


def test_interleaved_commands_preserve_identity_through_undo_cycle(state, stack):
    tag_x = _tag(time_seconds=1.0)
    stack.push(AddTagCommand("m1", "s1", "tt1", tag_x))
    assert _tags(state)[0] is tag_x

    stack.push(DeleteTagCommand("m1", "s1", "tt1", 0))
    assert _tags(state) == []

    stack.undo()  # undo delete — tag_x back
    tags = _tags(state)
    assert len(tags) == 1
    assert tags[0] is tag_x

    stack.undo()  # undo add — tag_x gone
    assert _tags(state) == []

    stack.redo()  # redo add — tag_x back with same identity
    tags = _tags(state)
    assert len(tags) == 1
    assert tags[0] is tag_x

    stack.redo()  # redo delete — tag_x gone again
    assert _tags(state) == []
