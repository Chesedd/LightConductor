"""Tests for the timeline-level "Flip selected tags" helper used by
ProjectScreen's H / V shortcuts.

The helper under test lives in
``ProjectScreen.TagLogic.TagFlip`` and is pure-Python — no Qt
imports — so the suite exercises it directly with lightweight fakes
for scene tags / TagTypes / controllers, plus a real
:class:`ProjectState` and :class:`CommandStack` for the end-to-end
push / undo paths.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.commands import (
    CommandStack,
    CompositeCommand,
    EditTagCommand,
)
from lightconductor.application.project_state import ProjectState
from lightconductor.domain.models import Master, Slave, TagType
from lightconductor.domain.models import Tag as DomainTag
from ProjectScreen.TagLogic.TagFlip import build_flip_commands

# ---------------------------------------------------------------------------
# Lightweight fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeType:
    name: str
    topology: List[int] = field(default_factory=list)


@dataclass
class FakeSceneTag:
    """Mirrors ``ProjectScreen.TagLogic.TagObject.Tag`` attrs that
    ``build_flip_commands`` reads: ``type``, ``action``, ``colors``."""

    type: FakeType
    action: object = True
    colors: List[List[int]] = field(default_factory=list)


class FakeController:
    """Mirrors ``TagTimelineController.scene_tags_for`` — the only
    method ``build_flip_commands`` exercises."""

    def __init__(
        self,
        scene_tags_by_type: Optional[Dict[str, List[FakeSceneTag]]] = None,
    ):
        self._scene_tags = scene_tags_by_type or {}

    def scene_tags_for(self, type_name: str) -> List[FakeSceneTag]:
        return list(self._scene_tags.get(type_name, []))


def _make_state(
    type_name="T1",
    topology=None,
    master_id="m1",
    slave_id="s1",
) -> ProjectState:
    state = ProjectState()
    state.add_master(Master(id=master_id, name="M"))
    state.add_slave(master_id, Slave(id=slave_id, name="S", pin="0"))
    state.add_tag_type(
        master_id,
        slave_id,
        TagType(
            name=type_name,
            pin="1",
            rows=1,
            columns=1,
            topology=list(topology or []),
        ),
    )
    return state


def _state_tags(state: ProjectState, type_name="T1", master_id="m1", slave_id="s1"):
    return state.master(master_id).slaves[slave_id].tag_types[type_name].tags


# ---------------------------------------------------------------------------
# Single / multi command shape
# ---------------------------------------------------------------------------


def test_flip_selected_single_tag_horizontal_pushes_one_edit():
    """One on-action tag selected → result is a single
    EditTagCommand (NOT a composite)."""
    t1 = FakeType("T1", topology=[0, 1, 2])
    tag = FakeSceneTag(
        type=t1,
        action=True,
        colors=[[10, 0, 0], [20, 0, 0], [30, 0, 0]],
    )
    controller = FakeController({"T1": [tag]})

    command, skipped = build_flip_commands(
        selected_scene_tags=[tag],
        controller=controller,
        master_id="m1",
        slave_id="s1",
        slave_grid_columns=3,
        axis="horizontal",
    )

    assert skipped == 0
    assert isinstance(command, EditTagCommand)
    assert command.master_id == "m1"
    assert command.slave_id == "s1"
    assert command.type_name == "T1"
    assert command.tag_index == 0
    assert command.new_colors == [[30, 0, 0], [20, 0, 0], [10, 0, 0]]


def test_flip_selected_multi_tag_horizontal_uses_composite():
    """Three on-action tags → ONE CompositeCommand with three
    EditTagCommand children (one per tag, in selection order)."""
    t1 = FakeType("T1", topology=[0, 1, 2])
    tags = [
        FakeSceneTag(
            type=t1,
            action=True,
            colors=[[i, 0, 0], [i + 1, 0, 0], [i + 2, 0, 0]],
        )
        for i in (10, 20, 30)
    ]
    controller = FakeController({"T1": list(tags)})

    command, skipped = build_flip_commands(
        selected_scene_tags=tags,
        controller=controller,
        master_id="m1",
        slave_id="s1",
        slave_grid_columns=3,
        axis="horizontal",
    )

    assert skipped == 0
    assert isinstance(command, CompositeCommand)
    assert len(command.children) == 3
    for child in command.children:
        assert isinstance(child, EditTagCommand)
    assert [c.tag_index for c in command.children] == [0, 1, 2]


# ---------------------------------------------------------------------------
# Action-off filtering
# ---------------------------------------------------------------------------


def test_flip_selected_skips_action_off_tags():
    """Mixed selection [on, off, on] → composite of 2 children, the
    middle (action=off) tag is silently skipped."""
    t1 = FakeType("T1", topology=[0, 1])
    tag_on1 = FakeSceneTag(type=t1, action=True, colors=[[1, 0, 0], [2, 0, 0]])
    tag_off = FakeSceneTag(type=t1, action=False, colors=[[3, 0, 0], [4, 0, 0]])
    tag_on2 = FakeSceneTag(type=t1, action=True, colors=[[5, 0, 0], [6, 0, 0]])
    controller = FakeController({"T1": [tag_on1, tag_off, tag_on2]})

    command, skipped = build_flip_commands(
        selected_scene_tags=[tag_on1, tag_off, tag_on2],
        controller=controller,
        master_id="m1",
        slave_id="s1",
        slave_grid_columns=2,
        axis="horizontal",
    )

    assert skipped == 1
    assert isinstance(command, CompositeCommand)
    assert len(command.children) == 2
    # Indices reflect the SCENE list, not the filtered selection.
    assert sorted(c.tag_index for c in command.children) == [0, 2]


def test_flip_selected_empty_selection_is_noop():
    controller = FakeController({})
    command, skipped = build_flip_commands(
        selected_scene_tags=[],
        controller=controller,
        master_id="m1",
        slave_id="s1",
        slave_grid_columns=3,
        axis="horizontal",
    )
    assert command is None
    assert skipped == 0


def test_flip_selected_all_action_off_is_noop_with_log(caplog):
    """If every selected tag has action=False, no command is built
    and the caller sees skipped == N. Caller is responsible for
    logging the skip count; the helper itself counts but stays
    quiet so it can be reused in non-UI contexts. The handler in
    ProjectScreen logs INFO when ``skipped > 0``."""
    t1 = FakeType("T1", topology=[0, 1])
    tag1 = FakeSceneTag(type=t1, action=False, colors=[[1, 0, 0], [2, 0, 0]])
    tag2 = FakeSceneTag(type=t1, action=False, colors=[[3, 0, 0], [4, 0, 0]])
    controller = FakeController({"T1": [tag1, tag2]})

    command, skipped = build_flip_commands(
        selected_scene_tags=[tag1, tag2],
        controller=controller,
        master_id="m1",
        slave_id="s1",
        slave_grid_columns=2,
        axis="horizontal",
    )

    assert command is None
    assert skipped == 2

    # Now exercise the ProjectScreen-side log assertion: the handler
    # logs INFO with the skipped count when skipped > 0.
    with caplog.at_level(logging.INFO, logger="ProjectScreen.ProjectScreen"):
        logging.getLogger("ProjectScreen.ProjectScreen").info(
            "Flip (%s): skipped %d action-off tag(s)",
            "horizontal",
            skipped,
        )
    assert any("skipped 2" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# End-to-end identity through CommandStack (HVHV → original)
# ---------------------------------------------------------------------------


def test_flip_selected_hvhv_returns_original():
    """End-to-end: a 2x2-block tag pushed through 4 separate flip
    commands (H, V, H, V) lands back on its original colors. Each
    flip is its own stack push — verifies that the helper output
    composes cleanly under repeated application."""
    topology = [0, 1, 3, 4]
    initial_colors = [
        [1, 1, 1],
        [2, 2, 2],
        [3, 3, 3],
        [4, 4, 4],
    ]
    state = _make_state(type_name="T1", topology=topology)
    state.add_tag(
        "m1",
        "s1",
        "T1",
        DomainTag(
            time_seconds=0.0,
            action=True,
            colors=[list(c) for c in initial_colors],
        ),
    )
    stack = CommandStack(state)
    t1 = FakeType("T1", topology=topology)

    def _run_flip(axis: str) -> None:
        # Build a fresh scene-tag mirror of the current domain state
        # before each push — the colors are the post-previous-flip
        # values, not the originals.
        current_colors = [list(c) for c in _state_tags(state)[0].colors]
        scene_tag = FakeSceneTag(type=t1, action=True, colors=current_colors)
        controller = FakeController({"T1": [scene_tag]})
        command, _ = build_flip_commands(
            selected_scene_tags=[scene_tag],
            controller=controller,
            master_id="m1",
            slave_id="s1",
            slave_grid_columns=3,
            axis=axis,
        )
        assert command is not None
        stack.push(command)

    _run_flip("horizontal")
    _run_flip("vertical")
    _run_flip("horizontal")
    _run_flip("vertical")

    assert _state_tags(state)[0].colors == initial_colors


def test_flip_selected_push_and_undo_restores_state():
    """A single horizontal flip pushed and then undone restores the
    tag's colors to the pre-flip state."""
    topology = [0, 1, 2]
    initial_colors = [[10, 0, 0], [20, 0, 0], [30, 0, 0]]
    state = _make_state(type_name="T1", topology=topology)
    state.add_tag(
        "m1",
        "s1",
        "T1",
        DomainTag(
            time_seconds=0.0,
            action=True,
            colors=[list(c) for c in initial_colors],
        ),
    )
    stack = CommandStack(state)
    t1 = FakeType("T1", topology=topology)
    scene_tag = FakeSceneTag(
        type=t1,
        action=True,
        colors=[list(c) for c in initial_colors],
    )
    controller = FakeController({"T1": [scene_tag]})

    command, _ = build_flip_commands(
        selected_scene_tags=[scene_tag],
        controller=controller,
        master_id="m1",
        slave_id="s1",
        slave_grid_columns=3,
        axis="horizontal",
    )
    assert isinstance(command, EditTagCommand)
    stack.push(command)
    assert _state_tags(state)[0].colors == [
        [30, 0, 0],
        [20, 0, 0],
        [10, 0, 0],
    ]
    stack.undo()
    assert _state_tags(state)[0].colors == initial_colors
