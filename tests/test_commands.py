import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.commands import (
    AddMasterCommand,
    AddOrReplaceTagCommand,
    AddSlaveCommand,
    AddTagCommand,
    AddTagTypeCommand,
    CompositeCommand,
    DeleteSlaveCommand,
    DeleteTagCommand,
    DeleteTagTypeCommand,
    EditRangeCommand,
    EditTagCommand,
    MoveTagCommand,
    TopologyCollisionError,
    UpdateMasterIpCommand,
)
from lightconductor.application.project_state import (
    MasterAdded,
    MasterUpdated,
    ProjectState,
    SlaveAdded,
    SlaveRemoved,
    TagAdded,
    TagRemoved,
    TagTypeAdded,
    TagTypeRemoved,
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


def test_move_tag_with_identity_resolves_to_current_index(state):
    _seed(state, [1.0, 2.0, 3.0])
    target = _tags(state)[1]
    tid = id(target)
    cmd = MoveTagCommand(
        "m1",
        "s1",
        "tt1",
        tag_index=1,
        new_time_seconds=5.0,
        tag_identity=tid,
    )
    # Insert a tag BEFORE execute so tag_index hint becomes stale:
    # the target (time=2.0) is now at index 2, not 1.
    inserted = _tag(time_seconds=0.5)
    state.add_tag("m1", "s1", "tt1", inserted)
    assert [t.time_seconds for t in _tags(state)] == [0.5, 1.0, 2.0, 3.0]
    assert _tags(state)[2] is target

    cmd.execute(state)

    tags = _tags(state)
    assert [t.time_seconds for t in tags] == [0.5, 1.0, 3.0, 5.0]
    # Identity-matched tag moved to 5.0; the tag we inserted at 0.5 untouched.
    assert tags[3] is target
    assert tags[0] is inserted

    cmd.undo(state)

    tags = _tags(state)
    assert [t.time_seconds for t in tags] == [0.5, 1.0, 2.0, 3.0]
    assert tags[2] is target


def test_move_tag_without_identity_uses_index(state):
    _seed(state, [1.0, 2.0, 3.0])
    # Insert a tag BEFORE execute: tags becomes [0.5, 1.0, 2.0, 3.0].
    state.add_tag("m1", "s1", "tt1", _tag(time_seconds=0.5))
    assert [t.time_seconds for t in _tags(state)] == [0.5, 1.0, 2.0, 3.0]
    # With tag_identity=None, tag_index=1 moves the tag at index 1
    # (time=1.0), not the one originally at index 1 (time=2.0).
    moved_by_index = _tags(state)[1]
    cmd = MoveTagCommand(
        "m1",
        "s1",
        "tt1",
        tag_index=1,
        new_time_seconds=5.0,
    )

    cmd.execute(state)

    tags = _tags(state)
    assert [t.time_seconds for t in tags] == [0.5, 2.0, 3.0, 5.0]
    assert tags[3] is moved_by_index


def test_move_tag_with_missing_identity_raises(state):
    _seed(state, [1.0, 2.0, 3.0])
    cmd = MoveTagCommand(
        "m1",
        "s1",
        "tt1",
        tag_index=0,
        new_time_seconds=5.0,
        tag_identity=9999,
    )

    with pytest.raises(IndexError):
        cmd.execute(state)


def test_composite_bulk_move_preserves_identities(state):
    _seed(state, [1.0, 2.0, 3.0, 4.0])
    tags = _tags(state)
    ref_a, ref_b, ref_c, ref_d = tags[0], tags[1], tags[2], tags[3]
    children = [
        MoveTagCommand(
            "m1",
            "s1",
            "tt1",
            tag_index=0,
            new_time_seconds=10.0,
            tag_identity=id(ref_a),
        ),
        MoveTagCommand(
            "m1",
            "s1",
            "tt1",
            tag_index=2,
            new_time_seconds=20.0,
            tag_identity=id(ref_c),
        ),
        MoveTagCommand(
            "m1",
            "s1",
            "tt1",
            tag_index=3,
            new_time_seconds=30.0,
            tag_identity=id(ref_d),
        ),
    ]
    composite = CompositeCommand(children=children)

    composite.execute(state)

    tags_after = _tags(state)
    by_identity = {id(t): t.time_seconds for t in tags_after}
    assert by_identity[id(ref_a)] == 10.0
    assert by_identity[id(ref_b)] == 2.0
    assert by_identity[id(ref_c)] == 20.0
    assert by_identity[id(ref_d)] == 30.0

    composite.undo(state)

    tags_restored = _tags(state)
    assert [t.time_seconds for t in tags_restored] == [1.0, 2.0, 3.0, 4.0]
    assert tags_restored[0] is ref_a
    assert tags_restored[1] is ref_b
    assert tags_restored[2] is ref_c
    assert tags_restored[3] is ref_d


# ---------------------------------------------------------------------------
# EditRangeCommand
# ---------------------------------------------------------------------------


def test_edit_range_execute_updates_pin_and_color(state):
    tag_type = _tag_type_of(state)
    assert tag_type.pin == "0"
    assert tag_type.color == [1, 1, 1]
    events = _capture(state)
    cmd = EditRangeCommand(
        "m1",
        "s1",
        "tt1",
        new_pin="5",
        new_color=[9, 9, 9],
    )

    cmd.execute(state)

    assert tag_type.pin == "5"
    assert tag_type.color == [9, 9, 9]
    assert len(events) == 1
    assert isinstance(events[0], TagTypeUpdated)


def test_edit_range_undo_restores_previous_values(state):
    tag_type = _tag_type_of(state)
    cmd = EditRangeCommand(
        "m1",
        "s1",
        "tt1",
        new_pin="5",
        new_color=[9, 9, 9],
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


# ---------------------------------------------------------------------------
# AddMasterCommand
# ---------------------------------------------------------------------------


def test_add_master_execute_adds_master():
    s = ProjectState()
    new_master = _master("m2", name="Master 2")
    cmd = AddMasterCommand(new_master)

    cmd.execute(s)

    assert s.has_master("m2")
    assert s.master("m2") is new_master


def test_add_master_undo_removes_master():
    s = ProjectState()
    cmd = AddMasterCommand(_master("m2"))
    cmd.execute(s)

    cmd.undo(s)

    assert not s.has_master("m2")


def test_add_master_execute_emits_master_added_event():
    s = ProjectState()
    events = _capture(s)
    cmd = AddMasterCommand(_master("m2"))

    cmd.execute(s)

    master_added = [ev for ev in events if isinstance(ev, MasterAdded)]
    assert len(master_added) == 1
    assert master_added[0].master_id == "m2"


# ---------------------------------------------------------------------------
# AddSlaveCommand
# ---------------------------------------------------------------------------


def test_add_slave_execute_adds_slave(state):
    new_slave = _slave("s2", name="Slave 2", pin="3")
    cmd = AddSlaveCommand("m1", new_slave)

    cmd.execute(state)

    assert "s2" in state.master("m1").slaves
    assert state.master("m1").slaves["s2"] is new_slave


def test_add_slave_undo_removes_slave(state):
    cmd = AddSlaveCommand("m1", _slave("s2", pin="3"))
    cmd.execute(state)

    cmd.undo(state)

    assert "s2" not in state.master("m1").slaves


def test_add_slave_execute_emits_slave_added_event(state):
    events = _capture(state)
    cmd = AddSlaveCommand("m1", _slave("s2", pin="3"))

    cmd.execute(state)

    slave_added = [ev for ev in events if isinstance(ev, SlaveAdded)]
    assert len(slave_added) == 1
    assert slave_added[0].master_id == "m1"
    assert slave_added[0].slave_id == "s2"


# ---------------------------------------------------------------------------
# DeleteSlaveCommand
# ---------------------------------------------------------------------------


def test_delete_slave_execute_removes_slave(state):
    cmd = DeleteSlaveCommand("m1", "s1")

    cmd.execute(state)

    assert "s1" not in state.master("m1").slaves
    assert cmd._deleted_slave is not None
    assert cmd._deleted_slave.id == "s1"


def test_delete_slave_undo_restores_same_slave_identity(state):
    original_slave = state.master("m1").slaves["s1"]
    cmd = DeleteSlaveCommand("m1", "s1")
    cmd.execute(state)

    cmd.undo(state)

    assert state.master("m1").slaves["s1"] is original_slave
    assert cmd._deleted_slave is None


def test_delete_slave_undo_restores_nested_tag_types_and_tags(state):
    _seed(state, [0.0, 1.0, 2.0])
    original_slave = state.master("m1").slaves["s1"]
    original_tt = original_slave.tag_types["tt1"]
    original_tags = list(original_tt.tags)
    cmd = DeleteSlaveCommand("m1", "s1")
    cmd.execute(state)

    cmd.undo(state)

    restored_slave = state.master("m1").slaves["s1"]
    assert restored_slave is original_slave
    assert restored_slave.tag_types["tt1"] is original_tt
    assert list(restored_slave.tag_types["tt1"].tags) == original_tags


def test_delete_slave_execute_emits_slave_removed_event(state):
    events = _capture(state)
    cmd = DeleteSlaveCommand("m1", "s1")

    cmd.execute(state)

    slave_removed = [ev for ev in events if isinstance(ev, SlaveRemoved)]
    assert len(slave_removed) == 1
    assert slave_removed[0].slave_id == "s1"


def test_delete_slave_undo_before_execute_raises_runtime_error(state):
    cmd = DeleteSlaveCommand("m1", "s1")

    with pytest.raises(RuntimeError):
        cmd.undo(state)


# ---------------------------------------------------------------------------
# AddTagTypeCommand
# ---------------------------------------------------------------------------


def test_add_tag_type_execute_adds_tag_type(state):
    new_tt = _tag_type(name="tt2", pin="4")
    cmd = AddTagTypeCommand("m1", "s1", new_tt)

    cmd.execute(state)

    assert "tt2" in state.master("m1").slaves["s1"].tag_types
    assert state.master("m1").slaves["s1"].tag_types["tt2"] is new_tt


def test_add_tag_type_undo_removes_tag_type(state):
    cmd = AddTagTypeCommand("m1", "s1", _tag_type(name="tt2", pin="4"))
    cmd.execute(state)

    cmd.undo(state)

    assert "tt2" not in state.master("m1").slaves["s1"].tag_types


def test_add_tag_type_execute_emits_tag_type_added_event(state):
    events = _capture(state)
    cmd = AddTagTypeCommand("m1", "s1", _tag_type(name="tt2", pin="4"))

    cmd.execute(state)

    tt_added = [ev for ev in events if isinstance(ev, TagTypeAdded)]
    assert len(tt_added) == 1
    assert tt_added[0].type_name == "tt2"


def test_add_tag_type_collision_raises(state):
    existing = state.master("m1").slaves["s1"].tag_types["tt1"]
    existing.topology = [0, 1, 2]
    new_tt = TagType(name="tt2", pin="4", rows=1, columns=2)
    new_tt.topology = [2, 3]
    cmd = AddTagTypeCommand("m1", "s1", new_tt)

    with pytest.raises(TopologyCollisionError) as excinfo:
        cmd.execute(state)

    assert excinfo.value.colliding_cells == frozenset({2})
    assert excinfo.value.master_id == "m1"
    assert excinfo.value.slave_id == "s1"
    assert excinfo.value.type_name == "tt2"
    assert "tt2" not in state.master("m1").slaves["s1"].tag_types


def test_add_tag_type_no_collision_succeeds(state):
    existing = state.master("m1").slaves["s1"].tag_types["tt1"]
    existing.topology = [0, 1]
    new_tt = TagType(name="tt2", pin="4", rows=1, columns=2)
    new_tt.topology = [2, 3]
    cmd = AddTagTypeCommand("m1", "s1", new_tt)

    cmd.execute(state)

    tag_types = state.master("m1").slaves["s1"].tag_types
    assert "tt1" in tag_types
    assert "tt2" in tag_types
    assert tag_types["tt2"] is new_tt


def test_add_tag_type_same_name_not_self_collision(state):
    # When the new TagType has the same name as an existing one,
    # the collision check must skip self-comparison. The add then
    # fails with ValueError from ProjectState.add_tag_type (which
    # rejects duplicate names), NOT with TopologyCollisionError.
    existing = state.master("m1").slaves["s1"].tag_types["tt1"]
    existing.topology = [0, 1]
    same_name = TagType(name="tt1", pin="9", rows=1, columns=2)
    same_name.topology = [0, 1]
    cmd = AddTagTypeCommand("m1", "s1", same_name)

    with pytest.raises(ValueError):
        cmd.execute(state)


# ---------------------------------------------------------------------------
# DeleteTagTypeCommand
# ---------------------------------------------------------------------------


def test_delete_tag_type_execute_removes_tag_type(state):
    cmd = DeleteTagTypeCommand("m1", "s1", "tt1")

    cmd.execute(state)

    assert "tt1" not in state.master("m1").slaves["s1"].tag_types
    assert cmd._deleted_tag_type is not None
    assert cmd._deleted_tag_type.name == "tt1"


def test_delete_tag_type_undo_restores_same_tag_type_with_tags(state):
    _seed(state, [0.0, 1.0, 2.0])
    original_tt = state.master("m1").slaves["s1"].tag_types["tt1"]
    original_tags = list(original_tt.tags)
    cmd = DeleteTagTypeCommand("m1", "s1", "tt1")
    cmd.execute(state)

    cmd.undo(state)

    restored_tt = state.master("m1").slaves["s1"].tag_types["tt1"]
    assert restored_tt is original_tt
    assert list(restored_tt.tags) == original_tags
    assert cmd._deleted_tag_type is None


def test_delete_tag_type_execute_emits_tag_type_removed_event(state):
    events = _capture(state)
    cmd = DeleteTagTypeCommand("m1", "s1", "tt1")

    cmd.execute(state)

    tt_removed = [ev for ev in events if isinstance(ev, TagTypeRemoved)]
    assert len(tt_removed) == 1
    assert tt_removed[0].type_name == "tt1"


def test_delete_tag_type_undo_before_execute_raises_runtime_error(state):
    cmd = DeleteTagTypeCommand("m1", "s1", "tt1")

    with pytest.raises(RuntimeError):
        cmd.undo(state)


# ---------------------------------------------------------------------------
# EditTagCommand
# ---------------------------------------------------------------------------


def test_edit_tag_execute_changes_time_repositions_and_undo_restores(state):
    _seed(state, [0.0, 1.0, 2.0])
    tag_ref = _tags(state)[0]
    cmd = EditTagCommand(
        "m1",
        "s1",
        "tt1",
        tag_index=0,
        new_time_seconds=1.5,
    )

    cmd.execute(state)

    tags = _tags(state)
    assert [t.time_seconds for t in tags] == [1.0, 1.5, 2.0]
    assert tags[1] is tag_ref

    cmd.undo(state)

    tags = _tags(state)
    assert [t.time_seconds for t in tags] == [0.0, 1.0, 2.0]
    assert tags[0] is tag_ref


def test_edit_tag_execute_changes_only_action(state):
    _seed(state, [0.0, 1.0])
    tags = _tags(state)
    tags[0].action = True
    tags[1].action = True
    cmd = EditTagCommand(
        "m1",
        "s1",
        "tt1",
        tag_index=1,
        new_time_seconds=None,
        new_action=False,
        new_colors=None,
    )

    cmd.execute(state)

    tags_after = _tags(state)
    assert [t.time_seconds for t in tags_after] == [0.0, 1.0]
    assert tags_after[1].action is False
    assert tags_after[0].action is True

    cmd.undo(state)

    tags_restored = _tags(state)
    assert tags_restored[1].action is True


def test_edit_tag_execute_changes_only_colors_and_old_colors_is_copy(state):
    _seed(state, [0.0])
    tag = _tags(state)[0]
    original_colors = [[10, 20, 30]]
    tag.colors = list(original_colors)
    cmd = EditTagCommand(
        "m1",
        "s1",
        "tt1",
        tag_index=0,
        new_colors=[[99, 99, 99]],
    )

    cmd.execute(state)

    # Mutate the tag's current colors after capture -- old copy must not be affected.
    tag.colors.append([7, 7, 7])
    # And _old_colors must be a distinct list from what we passed on the tag.
    assert cmd._old_colors == [[10, 20, 30]]

    cmd.undo(state)

    restored = _tags(state)[0]
    assert restored.colors == [[10, 20, 30]]


def test_edit_tag_execute_changes_all_three_fields_and_undo_restores_all(state):
    _seed(state, [0.0, 2.0])
    tag = _tags(state)[0]
    tag.action = True
    tag.colors = [[1, 2, 3]]
    cmd = EditTagCommand(
        "m1",
        "s1",
        "tt1",
        tag_index=0,
        new_time_seconds=1.5,
        new_action=False,
        new_colors=[[9, 9, 9]],
    )

    cmd.execute(state)

    tags = _tags(state)
    assert [t.time_seconds for t in tags] == [1.5, 2.0]
    assert tags[0] is tag
    assert tag.action is False
    assert tag.colors == [[9, 9, 9]]

    cmd.undo(state)

    tags = _tags(state)
    assert [t.time_seconds for t in tags] == [0.0, 2.0]
    assert tags[0] is tag
    assert tag.action is True
    assert tag.colors == [[1, 2, 3]]


def test_edit_tag_execute_out_of_range_raises_index_error(state):
    _seed(state, [0.0])
    cmd = EditTagCommand(
        "m1",
        "s1",
        "tt1",
        tag_index=5,
        new_time_seconds=1.0,
    )

    with pytest.raises(IndexError):
        cmd.execute(state)


def test_edit_tag_undo_before_execute_raises_runtime_error(state):
    cmd = EditTagCommand(
        "m1",
        "s1",
        "tt1",
        tag_index=0,
        new_time_seconds=1.0,
    )

    with pytest.raises(RuntimeError):
        cmd.undo(state)


# ---------------------------------------------------------------------------
# AddOrReplaceTagCommand
# ---------------------------------------------------------------------------


def test_add_or_replace_tag_adds_when_no_collision(state):
    _seed(state, [0.0, 2.0])
    new_tag = _tag(time_seconds=1.0)
    cmd = AddOrReplaceTagCommand("m1", "s1", "tt1", new_tag)

    cmd.execute(state)

    tags = _tags(state)
    assert [t.time_seconds for t in tags] == [0.0, 1.0, 2.0]
    assert tags[1] is new_tag
    assert cmd._replaced_old_tag is None


def test_add_or_replace_tag_replaces_on_exact_time_collision(state):
    _seed(state, [0.0, 1.0, 2.0])
    tags_before = _tags(state)
    first = tags_before[0]
    third = tags_before[2]
    victim = tags_before[1]
    new_tag = _tag(time_seconds=1.0, action=False)
    cmd = AddOrReplaceTagCommand("m1", "s1", "tt1", new_tag)

    cmd.execute(state)

    tags = _tags(state)
    assert [t.time_seconds for t in tags] == [0.0, 1.0, 2.0]
    assert tags[0] is first
    assert tags[1] is new_tag
    assert tags[2] is third
    assert cmd._replaced_old_tag is victim
    assert cmd._replaced_old_index == 1


def test_add_or_replace_tag_undo_restores_original(state):
    _seed(state, [0.0, 1.0, 2.0])
    original = _tags(state)[1]
    new_tag = _tag(time_seconds=1.0, action=False)
    cmd = AddOrReplaceTagCommand("m1", "s1", "tt1", new_tag)
    cmd.execute(state)

    cmd.undo(state)

    tags = _tags(state)
    assert [t.time_seconds for t in tags] == [0.0, 1.0, 2.0]
    assert tags[1] is original
    assert cmd._applied_index is None
    assert cmd._replaced_old_tag is None


def test_add_or_replace_tag_undo_after_pure_add_removes_only_new(state):
    _seed(state, [0.0, 2.0])
    new_tag = _tag(time_seconds=1.0)
    cmd = AddOrReplaceTagCommand("m1", "s1", "tt1", new_tag)
    cmd.execute(state)

    cmd.undo(state)

    assert [t.time_seconds for t in _tags(state)] == [0.0, 2.0]


def test_add_or_replace_tag_two_consecutive_undo_returns_to_empty(state):
    first = _tag(time_seconds=1.0, action=True)
    second = _tag(time_seconds=1.0, action=False)
    cmd_a = AddOrReplaceTagCommand("m1", "s1", "tt1", first)
    cmd_b = AddOrReplaceTagCommand("m1", "s1", "tt1", second)

    cmd_a.execute(state)
    cmd_b.execute(state)

    tags = _tags(state)
    assert len(tags) == 1
    assert tags[0] is second
    assert cmd_b._replaced_old_tag is first

    cmd_b.undo(state)
    tags = _tags(state)
    assert len(tags) == 1
    assert tags[0] is first

    cmd_a.undo(state)
    assert _tags(state) == []


def test_add_or_replace_tag_different_type_same_time_not_replaced(state):
    state.add_tag_type("m1", "s1", _tag_type("tt2", pin="1", color=[2, 2, 2]))
    state.add_tag("m1", "s1", "tt1", _tag(time_seconds=1.0, action=True))
    original_tt1 = state.master("m1").slaves["s1"].tag_types["tt1"].tags[0]
    new_tag = _tag(time_seconds=1.0, action=False)

    cmd = AddOrReplaceTagCommand("m1", "s1", "tt2", new_tag)
    cmd.execute(state)

    tt1_tags = state.master("m1").slaves["s1"].tag_types["tt1"].tags
    tt2_tags = state.master("m1").slaves["s1"].tag_types["tt2"].tags
    assert len(tt1_tags) == 1
    assert tt1_tags[0] is original_tt1
    assert len(tt2_tags) == 1
    assert tt2_tags[0] is new_tag
    assert cmd._replaced_old_tag is None


def test_add_or_replace_tag_undo_before_execute_raises_runtime_error(state):
    cmd = AddOrReplaceTagCommand(
        "m1",
        "s1",
        "tt1",
        _tag(time_seconds=1.0),
    )

    with pytest.raises(RuntimeError):
        cmd.undo(state)


# ---------------------------------------------------------------------------
# UpdateMasterIpCommand
# ---------------------------------------------------------------------------


def test_update_master_ip_execute_changes_ip_and_emits_master_updated(state):
    state.master("m1").ip = "10.0.0.1"
    events = _capture(state)
    cmd = UpdateMasterIpCommand(master_id="m1", new_ip="10.0.0.2")

    cmd.execute(state)

    assert state.master("m1").ip == "10.0.0.2"
    assert len(events) == 1
    assert isinstance(events[0], MasterUpdated)
    assert events[0].master_id == "m1"


def test_update_master_ip_undo_restores_old_ip_and_emits(state):
    state.master("m1").ip = "10.0.0.1"
    cmd = UpdateMasterIpCommand(master_id="m1", new_ip="10.0.0.2")
    cmd.execute(state)
    events = _capture(state)

    cmd.undo(state)

    assert state.master("m1").ip == "10.0.0.1"
    assert len(events) == 1
    assert isinstance(events[0], MasterUpdated)
    assert events[0].master_id == "m1"


def test_update_master_ip_redo_after_undo_reapplies_new_ip(state):
    state.master("m1").ip = "10.0.0.1"
    cmd = UpdateMasterIpCommand(master_id="m1", new_ip="10.0.0.2")
    cmd.execute(state)
    cmd.undo(state)

    cmd.execute(state)

    assert state.master("m1").ip == "10.0.0.2"


def test_update_master_ip_execute_unknown_master_raises_key_error(state):
    cmd = UpdateMasterIpCommand(master_id="missing", new_ip="10.0.0.2")

    with pytest.raises(KeyError):
        cmd.execute(state)


def test_update_master_ip_two_consecutive_push_undo_cycles_consistent(state):
    state.master("m1").ip = "10.0.0.1"
    cmd_a = UpdateMasterIpCommand(master_id="m1", new_ip="10.0.0.2")
    cmd_b = UpdateMasterIpCommand(master_id="m1", new_ip="10.0.0.3")

    cmd_a.execute(state)
    cmd_b.execute(state)
    assert state.master("m1").ip == "10.0.0.3"

    cmd_b.undo(state)
    assert state.master("m1").ip == "10.0.0.2"

    cmd_a.undo(state)
    assert state.master("m1").ip == "10.0.0.1"
