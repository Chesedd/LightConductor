"""Tests for the tag group-clipboard primitives used by
ProjectScreen's copy / cut / paste handlers.

The helpers under test live in
``ProjectScreen.TagLogic.TagClipboard`` and are pure-Python — no
Qt imports — so the suite exercises them directly with lightweight
fakes for scene tags / managers / controllers, plus a real
:class:`ProjectState` and :class:`CommandStack` for the end-to-end
push / rollback paths.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.commands import (
    AddOrReplaceTagCommand,
    CommandStack,
    CompositeCommand,
    DeleteTagCommand,
)
from lightconductor.application.project_state import ProjectState
from lightconductor.domain.models import Master, Slave, TagType
from ProjectScreen.TagLogic.TagClipboard import (
    GroupClipboard,
    TagClipboardEntry,
    build_cut_commands,
    build_paste_command,
    make_clipboard_from_selection,
)


# ---------------------------------------------------------------------------
# Lightweight fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeType:
    name: str


@dataclass
class FakeSceneTag:
    """Mirrors the attributes of ``ProjectScreen.TagLogic.TagObject.Tag``
    that the clipboard helpers actually read: ``time``, ``type``,
    ``action``, ``colors``."""

    time: float
    type: FakeType
    action: object = False
    colors: List[List[int]] = field(default_factory=list)


@dataclass
class FakeManager:
    """Mirrors ``TagManager.types`` lookup for the cross-slave guard."""

    types: Dict[str, object] = field(default_factory=dict)


class FakeController:
    """Mirrors ``TagTimelineController.scene_tags_for`` — the only
    method ``build_cut_commands`` exercises."""

    def __init__(self, scene_tags_by_type: Optional[Dict[str, List[FakeSceneTag]]] = None):
        self._scene_tags = scene_tags_by_type or {}

    def scene_tags_for(self, type_name: str) -> List[FakeSceneTag]:
        return list(self._scene_tags.get(type_name, []))


def _make_state(
    type_names=("T1",),
    master_id="m1",
    slave_id="s1",
) -> ProjectState:
    state = ProjectState()
    state.add_master(Master(id=master_id, name="M"))
    state.add_slave(master_id, Slave(id=slave_id, name="S", pin="0"))
    for i, name in enumerate(type_names):
        state.add_tag_type(
            master_id,
            slave_id,
            TagType(name=name, pin=str(i + 1), rows=1, columns=1),
        )
    return state


def _state_tags(state: ProjectState, type_name="T1", master_id="m1", slave_id="s1"):
    return state.master(master_id).slaves[slave_id].tag_types[type_name].tags


# ---------------------------------------------------------------------------
# make_clipboard_from_selection — copy semantics
# ---------------------------------------------------------------------------


def test_copy_with_empty_selection_is_noop():
    """No selection → no clipboard, helper returns None so the
    handler short-circuits before touching ``self._tag_clipboard``."""
    assert make_clipboard_from_selection([]) is None


def test_copy_single_tag_stores_one_entry_with_relative_zero():
    """Single-tag copy: the lone entry's ``relative_time`` is 0.0
    (it is its own anchor)."""
    t1 = FakeType("T1")
    selection = [FakeSceneTag(time=2.5, type=t1, action=True, colors=[[1, 2, 3]])]

    clipboard = make_clipboard_from_selection(selection)

    assert clipboard is not None
    assert len(clipboard.entries) == 1
    assert clipboard.entries[0].type_name == "T1"
    assert clipboard.entries[0].relative_time == 0.0
    assert clipboard.entries[0].action is True
    assert clipboard.entries[0].colors == ((1, 2, 3),)


def test_copy_group_relative_offsets_preserved_and_sorted():
    """Selection given out of order: clipboard entries come back
    sorted ascending by absolute time, with relatives anchored at
    the earliest tag."""
    t1 = FakeType("T1")
    selection = [
        FakeSceneTag(time=3.0, type=t1),
        FakeSceneTag(time=2.0, type=t1),
        FakeSceneTag(time=2.5, type=t1),
    ]

    clipboard = make_clipboard_from_selection(selection)

    assert clipboard is not None
    rels = [e.relative_time for e in clipboard.entries]
    assert rels == [0.0, 0.5, 1.0]


# ---------------------------------------------------------------------------
# build_paste_command — paste semantics
# ---------------------------------------------------------------------------


def test_paste_single_tag_at_cursor():
    """Single-entry clipboard pasted at cursor=10.0 produces one
    AddOrReplaceTagCommand whose tag.time_seconds == 10.0."""
    clipboard = GroupClipboard(
        entries=(
            TagClipboardEntry(
                type_name="T1",
                relative_time=0.0,
                action=False,
                colors=((0, 0, 0),),
            ),
        )
    )
    manager = FakeManager(types={"T1": object()})

    composite = build_paste_command(
        clipboard=clipboard,
        target_manager=manager,
        master_id="m1",
        slave_id="s1",
        anchor_time=10.0,
    )

    assert composite is not None
    assert len(composite.children) == 1
    cmd = composite.children[0]
    assert isinstance(cmd, AddOrReplaceTagCommand)
    assert cmd.tag.time_seconds == 10.0
    assert cmd.type_name == "T1"


def test_paste_group_shifts_to_cursor_preserving_offsets():
    """Group clipboard with relatives [0.0, 0.5, 1.0] pasted at
    cursor 7.25 produces three AddOrReplaceTagCommand children
    inside ONE CompositeCommand pushed once on the stack."""
    clipboard = GroupClipboard(
        entries=tuple(
            TagClipboardEntry(
                type_name="T1",
                relative_time=rel,
                action=False,
                colors=(),
            )
            for rel in (0.0, 0.5, 1.0)
        ),
    )
    manager = FakeManager(types={"T1": object()})
    state = _make_state(type_names=("T1",))
    stack = CommandStack(state)

    composite = build_paste_command(
        clipboard=clipboard,
        target_manager=manager,
        master_id="m1",
        slave_id="s1",
        anchor_time=7.25,
    )

    assert isinstance(composite, CompositeCommand)
    times = [c.tag.time_seconds for c in composite.children]
    assert times == [7.25, 7.75, 8.25]

    stack.push(composite)
    # All three landed via a single stack entry — one Ctrl+Z reverts
    # the whole group.
    assert stack.can_undo() is True
    assert [t.time_seconds for t in _state_tags(state)] == [7.25, 7.75, 8.25]
    stack.undo()
    assert _state_tags(state) == []


def test_paste_group_atomic_rollback_on_third_failure(monkeypatch):
    """If the third add_tag raises, the prior two are undone (state
    returns to pre-paste) and the exception propagates from
    CompositeCommand.execute. CommandStack.push therefore does NOT
    add the failed composite to the undo stack."""
    clipboard = GroupClipboard(
        entries=tuple(
            TagClipboardEntry(
                type_name="T1",
                relative_time=rel,
                action=False,
                colors=(),
            )
            for rel in (0.0, 0.5, 1.0)
        ),
    )
    manager = FakeManager(types={"T1": object()})
    state = _make_state(type_names=("T1",))
    stack = CommandStack(state)

    real_add_tag = state.add_tag
    call_counter = {"n": 0}

    def flaky_add_tag(*args, **kwargs):
        call_counter["n"] += 1
        if call_counter["n"] == 3:
            raise RuntimeError("simulated failure on third add")
        return real_add_tag(*args, **kwargs)

    monkeypatch.setattr(state, "add_tag", flaky_add_tag)

    composite = build_paste_command(
        clipboard=clipboard,
        target_manager=manager,
        master_id="m1",
        slave_id="s1",
        anchor_time=0.0,
    )
    assert composite is not None

    with pytest.raises(RuntimeError, match="simulated failure"):
        stack.push(composite)

    # Rollback restored pre-paste state and stack stayed clean.
    assert _state_tags(state) == []
    assert stack.can_undo() is False


# ---------------------------------------------------------------------------
# build_cut_commands — cut semantics
# ---------------------------------------------------------------------------


def test_cut_copies_then_deletes_atomically():
    """After cut: clipboard mirrors the selection, ONE
    CompositeCommand on the stack contains the deletes, and the
    state has those tags removed."""
    state = _make_state(type_names=("T1",))
    real_add_tag = state.add_tag
    real_add_tag("m1", "s1", "T1", _domain_tag(2.0))
    real_add_tag("m1", "s1", "T1", _domain_tag(2.5))

    t1 = FakeType("T1")
    scene_tags = [
        FakeSceneTag(time=2.0, type=t1),
        FakeSceneTag(time=2.5, type=t1),
    ]
    controller = FakeController({"T1": list(scene_tags)})
    stack = CommandStack(state)

    clipboard, composite = build_cut_commands(
        selected_scene_tags=scene_tags,
        controller=controller,
        master_id="m1",
        slave_id="s1",
    )

    assert clipboard is not None
    assert len(clipboard.entries) == 2
    assert isinstance(composite, CompositeCommand)
    stack.push(composite)
    assert _state_tags(state) == []
    # One composite => one undo entry => Ctrl+Z restores both.
    assert stack.can_undo() is True
    stack.undo()
    assert [t.time_seconds for t in _state_tags(state)] == [2.0, 2.5]


def test_cut_uses_descending_indices():
    """Selection at scene-indices [1, 4, 7] of one type produces
    DeleteTagCommand children with tag_index==7, 4, 1 in that order
    — required so each delete lands on a still-valid index."""
    t1 = FakeType("T1")
    # Scene tags occupy positions 1, 4, 7 within an 8-tag type list.
    full_scene = [FakeSceneTag(time=float(i), type=t1) for i in range(8)]
    selected = [full_scene[1], full_scene[4], full_scene[7]]
    controller = FakeController({"T1": full_scene})

    _, composite = build_cut_commands(
        selected_scene_tags=selected,
        controller=controller,
        master_id="m1",
        slave_id="s1",
    )

    assert composite is not None
    assert all(isinstance(c, DeleteTagCommand) for c in composite.children)
    assert [c.tag_index for c in composite.children] == [7, 4, 1]


# ---------------------------------------------------------------------------
# Cross-slave paste guard
# ---------------------------------------------------------------------------


def test_paste_cross_slave_single_type_target_has_type_succeeds():
    """Single-type clipboard + target manager that has the type →
    paste proceeds with N children."""
    clipboard = GroupClipboard(
        entries=tuple(
            TagClipboardEntry(
                type_name="T1",
                relative_time=rel,
                action=False,
                colors=(),
            )
            for rel in (0.0, 0.5)
        ),
    )
    target_manager = FakeManager(types={"T1": object(), "T_extra": object()})

    composite = build_paste_command(
        clipboard=clipboard,
        target_manager=target_manager,
        master_id="m2",
        slave_id="s2",
        anchor_time=0.0,
    )

    assert composite is not None
    assert len(composite.children) == 2
    assert all(isinstance(c, AddOrReplaceTagCommand) for c in composite.children)


def test_paste_cross_slave_single_type_target_lacks_type_logs_and_noops(caplog):
    """Single-type clipboard + target missing that type → no
    composite returned, INFO log mentions the blocked type."""
    clipboard = GroupClipboard(
        entries=(
            TagClipboardEntry(
                type_name="T1",
                relative_time=0.0,
                action=False,
                colors=(),
            ),
        )
    )
    assert clipboard.is_single_type is True
    target_manager = FakeManager(types={"T2": object()})

    state = _make_state(type_names=("T2",))
    stack = CommandStack(state)

    with caplog.at_level(logging.INFO, logger="ProjectScreen.TagLogic.TagClipboard"):
        composite = build_paste_command(
            clipboard=clipboard,
            target_manager=target_manager,
            master_id="m1",
            slave_id="s1",
            anchor_time=0.0,
        )

    assert composite is None
    # Nothing pushed: the handler would simply skip the push when
    # composite is None. Verify no accidental side effects via the
    # stack we built alongside.
    assert stack.can_undo() is False
    assert any("T1" in record.getMessage() for record in caplog.records), (
        f"expected T1 in blocked-types log, got {[r.getMessage() for r in caplog.records]}"
    )


def test_paste_cross_slave_mixed_types_blocked(caplog):
    """Mixed-type clipboard never satisfies the single-type
    fallback — even when the target has both types, the guard
    only proceeds when ``all_present`` already holds. With the
    target missing one of the two types, the paste is blocked."""
    clipboard = GroupClipboard(
        entries=(
            TagClipboardEntry(
                type_name="T1",
                relative_time=0.0,
                action=False,
                colors=(),
            ),
            TagClipboardEntry(
                type_name="T2",
                relative_time=0.5,
                action=False,
                colors=(),
            ),
        )
    )
    assert clipboard.is_single_type is False
    target_manager = FakeManager(types={"T1": object()})  # T2 missing

    with caplog.at_level(logging.INFO, logger="ProjectScreen.TagLogic.TagClipboard"):
        composite = build_paste_command(
            clipboard=clipboard,
            target_manager=target_manager,
            master_id="m1",
            slave_id="s1",
            anchor_time=0.0,
        )

    assert composite is None
    assert any(
        "T2" in record.getMessage() and "is_single_type=False" in record.getMessage()
        for record in caplog.records
    )


def test_paste_with_empty_clipboard_is_noop():
    """No copy → handler-equivalent path: build_paste_command on
    empty clipboard returns None, nothing pushed."""
    clipboard = GroupClipboard(entries=())
    target_manager = FakeManager(types={"T1": object()})

    composite = build_paste_command(
        clipboard=clipboard,
        target_manager=target_manager,
        master_id="m1",
        slave_id="s1",
        anchor_time=5.0,
    )

    assert composite is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _domain_tag(t: float, action: bool = False, colors=None):
    from lightconductor.domain.models import Tag as DomainTag

    return DomainTag(
        time_seconds=float(t),
        action=action,
        colors=list(colors) if colors is not None else [],
    )
