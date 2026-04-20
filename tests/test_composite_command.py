import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.commands import (
    AddTagCommand,
    CommandStack,
    CompositeCommand,
    DeleteTagCommand,
)
from lightconductor.application.project_state import ProjectState
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


def _tags(state, type_name="tt1"):
    return state.master("m1").slaves["s1"].tag_types[type_name].tags


def _seed(state, times, type_name="tt1"):
    for t in times:
        state.add_tag("m1", "s1", type_name, _tag(time_seconds=t))


# ---------------------------------------------------------------------------
# CompositeCommand
# ---------------------------------------------------------------------------


def test_empty_composite_execute_and_undo_are_noops(state):
    _seed(state, [0.0, 1.0])
    before = [t.time_seconds for t in _tags(state)]
    cmd = CompositeCommand(children=[])

    cmd.execute(state)
    assert [t.time_seconds for t in _tags(state)] == before

    cmd.undo(state)
    assert [t.time_seconds for t in _tags(state)] == before


def test_single_child_delegates_execute_and_undo(state):
    _seed(state, [0.0, 1.0, 2.0])
    cmd = CompositeCommand(children=[DeleteTagCommand("m1", "s1", "tt1", 1)])

    cmd.execute(state)
    assert [t.time_seconds for t in _tags(state)] == [0.0, 2.0]

    cmd.undo(state)
    assert [t.time_seconds for t in _tags(state)] == [0.0, 1.0, 2.0]


def test_multiple_children_execute_in_order(state):
    # Start with empty tag list.
    assert len(_tags(state)) == 0
    children = [
        AddTagCommand("m1", "s1", "tt1", _tag(time_seconds=0.0)),
        AddTagCommand("m1", "s1", "tt1", _tag(time_seconds=1.0)),
        AddTagCommand("m1", "s1", "tt1", _tag(time_seconds=2.0)),
    ]
    cmd = CompositeCommand(children=children)

    cmd.execute(state)

    assert len(_tags(state)) == 3
    assert sorted(t.time_seconds for t in _tags(state)) == [0.0, 1.0, 2.0]


def test_undo_reverses_children_in_reverse_order(state):
    _seed(state, [0.0, 1.0, 2.0, 3.0])
    children = [
        DeleteTagCommand("m1", "s1", "tt1", 2),
        DeleteTagCommand("m1", "s1", "tt1", 1),
    ]
    cmd = CompositeCommand(children=children)

    cmd.execute(state)
    assert [t.time_seconds for t in _tags(state)] == [0.0, 3.0]

    cmd.undo(state)
    assert [t.time_seconds for t in _tags(state)] == [0.0, 1.0, 2.0, 3.0]


def test_bulk_delete_descending_order_within_type(state):
    _seed(state, [1.0, 2.0, 3.0, 4.0, 5.0])
    # Delete indices 4, 2, 0 in descending order.
    children = [
        DeleteTagCommand("m1", "s1", "tt1", 4),
        DeleteTagCommand("m1", "s1", "tt1", 2),
        DeleteTagCommand("m1", "s1", "tt1", 0),
    ]
    cmd = CompositeCommand(children=children)

    cmd.execute(state)
    assert [t.time_seconds for t in _tags(state)] == [2.0, 4.0]

    cmd.undo(state)
    assert [t.time_seconds for t in _tags(state)] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_execute_failure_rolls_back_prior_children(state):
    _seed(state, [0.0, 1.0])
    tags_before = list(_tags(state))
    # First child is valid, second has out-of-range index.
    # Use index 0 (valid) then index 50 (out of range after one deletion).
    children = [
        DeleteTagCommand("m1", "s1", "tt1", 0),
        DeleteTagCommand("m1", "s1", "tt1", 50),
    ]
    cmd = CompositeCommand(children=children)

    with pytest.raises(IndexError):
        cmd.execute(state)

    # First child's effect should have been undone.
    tags_after = list(_tags(state))
    assert len(tags_after) == 2
    assert [t.time_seconds for t in tags_after] == [0.0, 1.0]
    # Identity preserved by DeleteTagCommand's reinsert.
    assert tags_after[0] is tags_before[0]
    assert tags_after[1] is tags_before[1]

    # _last_executed == -1, so undo is a no-op.
    assert cmd._last_executed == -1
    cmd.undo(state)
    assert [t.time_seconds for t in _tags(state)] == [0.0, 1.0]


def test_undo_without_execute_is_noop(state):
    _seed(state, [0.0, 1.0])
    before = [t.time_seconds for t in _tags(state)]
    cmd = CompositeCommand(
        children=[DeleteTagCommand("m1", "s1", "tt1", 0)],
    )

    # No execute(); undo should be a no-op.
    cmd.undo(state)

    assert [t.time_seconds for t in _tags(state)] == before


def test_redo_via_commandstack(state):
    _seed(state, [0.0, 1.0, 2.0, 3.0])
    stack = CommandStack(state)
    children = [
        DeleteTagCommand("m1", "s1", "tt1", 3),
        DeleteTagCommand("m1", "s1", "tt1", 0),
    ]

    stack.push(CompositeCommand(children=children))
    post_execute = [t.time_seconds for t in _tags(state)]
    assert post_execute == [1.0, 2.0]

    stack.undo()
    assert [t.time_seconds for t in _tags(state)] == [0.0, 1.0, 2.0, 3.0]

    stack.redo()
    assert [t.time_seconds for t in _tags(state)] == post_execute


def test_across_tag_types_interleaved(state):
    # Add second tag type "beta".
    state.add_tag_type(
        "m1",
        "s1",
        _tag_type(name="beta", pin="2", color=[2, 2, 2]),
    )
    # Seed "tt1" (alpha-ish) with 3 tags and "beta" with 1 tag.
    _seed(state, [0.0, 1.0, 2.0], type_name="tt1")
    _seed(state, [10.0], type_name="beta")

    # Keep identity refs.
    alpha_before = list(_tags(state, "tt1"))
    beta_before = list(_tags(state, "beta"))

    # Delete tt1 idx 1, tt1 idx 0, beta idx 0.
    children = [
        DeleteTagCommand("m1", "s1", "tt1", 1),
        DeleteTagCommand("m1", "s1", "tt1", 0),
        DeleteTagCommand("m1", "s1", "beta", 0),
    ]
    cmd = CompositeCommand(children=children)

    cmd.execute(state)

    assert [t.time_seconds for t in _tags(state, "tt1")] == [2.0]
    assert [t.time_seconds for t in _tags(state, "beta")] == []

    cmd.undo(state)

    alpha_after = list(_tags(state, "tt1"))
    beta_after = list(_tags(state, "beta"))
    assert [t.time_seconds for t in alpha_after] == [0.0, 1.0, 2.0]
    assert [t.time_seconds for t in beta_after] == [10.0]
    # Identity preserved.
    for orig, restored in zip(alpha_before, alpha_after, strict=True):
        assert orig is restored
    assert beta_before[0] is beta_after[0]


def test_identity_preserved_for_reinsertion(state):
    _seed(state, [0.0, 1.0])
    tags_before = list(_tags(state))
    ref0 = tags_before[0]
    ref1 = tags_before[1]

    children = [
        DeleteTagCommand("m1", "s1", "tt1", 1),
        DeleteTagCommand("m1", "s1", "tt1", 0),
    ]
    cmd = CompositeCommand(children=children)

    cmd.execute(state)
    assert len(_tags(state)) == 0

    cmd.undo(state)
    tags_after = list(_tags(state))
    assert len(tags_after) == 2
    assert tags_after[0] is ref0
    assert tags_after[1] is ref1
