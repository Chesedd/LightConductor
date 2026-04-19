import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.commands import (
    AddTagCommand,
    DeleteTagCommand,
    EditRangeCommand,
    MoveTagCommand,
)
from lightconductor.application.project_state import (
    ProjectState,
    TagAdded,
    TagRemoved,
    TagTypeUpdated,
    TagUpdated,
)
from lightconductor.domain.models import Master, Slave, Tag, TagType


def _master(master_id="m1", name="Master 1"):
    return Master(id=master_id, name=name)


def _slave(slave_id="s1", name="Slave 1", pin="0"):
    return Slave(id=slave_id, name=name, pin=pin)


def _tag_type(name="tt1", pin="1", rows=1, columns=1, color=None):
    tt = TagType(name=name, pin=pin, rows=rows, columns=columns)
    if color is not None:
        tt.color = color
    return tt


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
    s.add_tag_type("m1", "s1", _tag_type("tt1", pin="0", color=[1, 1, 1]))
    return s


def _tags(state):
    return state.master("m1").slaves["s1"].tag_types["tt1"].tags


def _tag_type_of(state):
    return state.master("m1").slaves["s1"].tag_types["tt1"]


def _seed(state, times):
    for t in times:
        state.add_tag("m1", "s1", "tt1", _tag(time_seconds=t))


def _capture(state):
    events = []
    state.subscribe(lambda ev: events.append(ev))
    return events


# ---------------------------------------------------------------------------
# AddTagCommand
# ---------------------------------------------------------------------------

def test_add_tag_execute_appends_tag_by_time(state):
    _seed(state, [0.0, 2.0])
    new_tag = _tag(time_seconds=1.0)
    cmd = AddTagCommand("m1", "s1", "tt1", new_tag)

    cmd.execute(state)

    assert [t.time_seconds for t in _tags(state)] == [0.0, 1.0, 2.0]
    assert cmd._applied_index == 1


def test_add_tag_undo_removes_tag(state):
    _seed(state, [0.0, 2.0])
    new_tag = _tag(time_seconds=1.0)
    cmd = AddTagCommand("m1", "s1", "tt1", new_tag)
    cmd.execute(state)

    cmd.undo(state)

    assert [t.time_seconds for t in _tags(state)] == [0.0, 2.0]
    assert cmd._applied_index is None


def test_add_tag_undo_before_execute_raises_runtime_error(state):
    cmd = AddTagCommand("m1", "s1", "tt1", _tag(time_seconds=1.0))

    with pytest.raises(RuntimeError):
        cmd.undo(state)


# ---------------------------------------------------------------------------
# DeleteTagCommand
# ---------------------------------------------------------------------------

def test_delete_tag_execute_removes_tag(state):
    _seed(state, [0.0, 1.0, 2.0])
    cmd = DeleteTagCommand("m1", "s1", "tt1", 1)

    cmd.execute(state)

    assert [t.time_seconds for t in _tags(state)] == [0.0, 2.0]
    assert cmd._deleted_tag is not None
    assert cmd._deleted_tag.time_seconds == 1.0


def test_delete_tag_undo_reinserts_same_tag_identity(state):
    _seed(state, [0.0, 1.0, 2.0])
    original = _tags(state)[1]
    cmd = DeleteTagCommand("m1", "s1", "tt1", 1)
    cmd.execute(state)

    cmd.undo(state)

    tags = _tags(state)
    assert len(tags) == 3
    assert tags[1] is original
    assert cmd._deleted_tag is None


def test_delete_tag_execute_out_of_range_raises_index_error(state):
    _seed(state, [0.0, 1.0])
    cmd = DeleteTagCommand("m1", "s1", "tt1", 5)

    with pytest.raises(IndexError):
        cmd.execute(state)


# ---------------------------------------------------------------------------
# MoveTagCommand
# ---------------------------------------------------------------------------

def test_move_tag_execute_updates_time_and_repositions(state):
    _seed(state, [0.0, 1.0, 2.0])
    cmd = MoveTagCommand("m1", "s1", "tt1", 0, new_time_seconds=1.5)

    cmd.execute(state)

    assert [t.time_seconds for t in _tags(state)] == [1.0, 1.5, 2.0]


def test_move_tag_undo_restores_original_time_and_position(state):
    _seed(state, [0.0, 1.0, 2.0])
    moved = _tags(state)[0]
    cmd = MoveTagCommand("m1", "s1", "tt1", 0, new_time_seconds=1.5)
    cmd.execute(state)

    cmd.undo(state)

    tags = _tags(state)
    assert [t.time_seconds for t in tags] == [0.0, 1.0, 2.0]
    assert tags[0] is moved


def test_move_tag_undo_after_multiple_repositions_uses_identity(state):
    _seed(state, [0.0, 1.0, 2.0])
    tags = _tags(state)
    original_a = tags[0]
    original_b = tags[1]
    original_c = tags[2]

    cmd_first = MoveTagCommand("m1", "s1", "tt1", 0, new_time_seconds=1.5)
    cmd_first.execute(state)
    assert [t.time_seconds for t in _tags(state)] == [1.0, 1.5, 2.0]

    cmd_second = MoveTagCommand("m1", "s1", "tt1", 2, new_time_seconds=0.5)
    cmd_second.execute(state)
    assert [t.time_seconds for t in _tags(state)] == [0.5, 1.0, 1.5]

    cmd_second.undo(state)
    assert [t.time_seconds for t in _tags(state)] == [1.0, 1.5, 2.0]

    cmd_first.undo(state)
    tags_final = _tags(state)
    assert [t.time_seconds for t in tags_final] == [0.0, 1.0, 2.0]
    assert tags_final[0] is original_a
    assert tags_final[1] is original_b
    assert tags_final[2] is original_c


def test_move_tag_execute_out_of_range_raises_index_error(state):
    _seed(state, [0.0, 1.0])
    cmd = MoveTagCommand("m1", "s1", "tt1", 10, new_time_seconds=0.5)

    with pytest.raises(IndexError):
        cmd.execute(state)


# ---------------------------------------------------------------------------
# EditRangeCommand
# ---------------------------------------------------------------------------

def test_edit_range_execute_updates_pin_and_color(state):
    tag_type = _tag_type_of(state)
    assert tag_type.pin == "0"
    assert tag_type.color == [1, 1, 1]
    events = _capture(state)
    cmd = EditRangeCommand(
        "m1", "s1", "tt1", new_pin="5", new_color=[9, 9, 9],
    )

    cmd.execute(state)

    assert tag_type.pin == "5"
    assert tag_type.color == [9, 9, 9]
    assert len(events) == 1
    assert isinstance(events[0], TagTypeUpdated)


def test_edit_range_undo_restores_previous_values(state):
    tag_type = _tag_type_of(state)
    cmd = EditRangeCommand(
        "m1", "s1", "tt1", new_pin="5", new_color=[9, 9, 9],
    )
    cmd.execute(state)
    events = _capture(state)

    cmd.undo(state)

    assert tag_type.pin == "0"
    assert tag_type.color == [1, 1, 1]
    assert len(events) == 1
    assert isinstance(events[0], TagTypeUpdated)


def test_edit_range_undo_before_execute_raises_runtime_error(state):
    cmd = EditRangeCommand("m1", "s1", "tt1", new_pin="5")

    with pytest.raises(RuntimeError):
        cmd.undo(state)


# ---------------------------------------------------------------------------
# Event capture
# ---------------------------------------------------------------------------

def test_add_tag_command_execute_emits_tag_added_event(state):
    events = _capture(state)
    cmd = AddTagCommand("m1", "s1", "tt1", _tag(time_seconds=0.25))

    cmd.execute(state)

    tag_added = [ev for ev in events if isinstance(ev, TagAdded)]
    assert len(tag_added) == 1
    assert tag_added[0].tag_index == 0


def test_delete_tag_command_execute_emits_tag_removed_event(state):
    _seed(state, [0.0, 1.0])
    events = _capture(state)
    cmd = DeleteTagCommand("m1", "s1", "tt1", 0)

    cmd.execute(state)

    tag_removed = [ev for ev in events if isinstance(ev, TagRemoved)]
    assert len(tag_removed) == 1
    assert tag_removed[0].tag_index == 0


def test_move_tag_command_execute_emits_tag_updated_event(state):
    _seed(state, [0.0, 1.0, 2.0])
    events = _capture(state)
    cmd = MoveTagCommand("m1", "s1", "tt1", 0, new_time_seconds=1.5)

    cmd.execute(state)

    tag_updated = [ev for ev in events if isinstance(ev, TagUpdated)]
    assert len(tag_updated) == 1
    assert tag_updated[0].tag_index == 1
