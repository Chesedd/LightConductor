"""Tests for the press-time selection-preservation contract that
the click-vs-drag dispatch in Tag.mousePressEvent depends on.

The bug under test (Phase 23, case "B"): pressing LMB without
modifiers on a tag that was already part of a multi-selection
used to call `controller.select_only(self)`, collapsing the
selection to one before `notify_drag_started` snapshotted the
group. The result was a singleton snapshot and lockstep mirror
had nothing to mirror — the group never moved.

Fix: when the press lands on a member of a multi-selection
without modifiers, leave the selection intact and let the
existing notify_drag_started snapshot all members.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from ProjectScreen.TagLogic.TagObject import Tag  # noqa: E402
from ProjectScreen.TagLogic.TagTimelineController import (  # noqa: E402
    TagTimelineController,
)

_app: QApplication | None = None


def _ensure_app() -> QApplication:
    global _app
    existing = QApplication.instance()
    if existing is not None:
        return existing  # type: ignore[return-value]
    _app = QApplication([])
    return _app


class _FakeEvent:
    """Stand-in for QGraphicsSceneMouseEvent — only the methods
    Tag.mousePressEvent / mouseReleaseEvent reach for."""

    def __init__(self, scene_pos: QPointF | None = None) -> None:
        self._accepted = False
        self._scene_pos = scene_pos if scene_pos is not None else QPointF(0.0, 0.0)

    def accept(self) -> None:
        self._accepted = True

    def ignore(self) -> None:
        self._accepted = False

    def isAccepted(self) -> bool:
        return self._accepted

    def scenePos(self) -> QPointF:
        return self._scene_pos


def _make_controller() -> TagTimelineController:
    # The real controller is safe to instantiate with all
    # collaborators set to None: it never subscribes when
    # state is None and the selection helpers under test
    # never touch plot_widget / manager / renderer. The only
    # thing that would touch Qt rendering is
    # _apply_selection_visual, and that short-circuits when
    # the tag's `type` attribute is None — which is the case
    # for every Tag we build below.
    return TagTimelineController(
        plot_widget=None,
        manager=None,
        renderer=None,
        state=None,
        project_window=None,
        master_id=None,
        slave_id=None,
        commands=None,
    )


def _make_tag_wired_to(controller: TagTimelineController, x: float) -> Tag:
    """Build a Tag whose manager.box.wave._tagController points
    at the supplied controller, mirroring the production
    resolution path in Tag.mousePressEvent."""
    wave = SimpleNamespace(_tagController=controller)
    box = SimpleNamespace(wave=wave)
    manager = SimpleNamespace(box=box, _project_window=None)
    return Tag(pos=QPointF(x, 0.0), movable=True, manager=manager)


def test_press_on_group_member_without_modifier_preserves_selection() -> None:
    """Plain LMB press on a tag that is already part of a
    multi-selection must NOT collapse the selection. Otherwise
    the subsequent notify_drag_started would snapshot only one
    tag and the group-drag mirror would have nothing to mirror.
    """
    _ensure_app()
    controller = _make_controller()
    tag_a = _make_tag_wired_to(controller, x=1.0)
    tag_b = _make_tag_wired_to(controller, x=2.0)
    # Seed the multi-selection directly to bypass any visual
    # plumbing — we are exercising the press-time decision, not
    # the selection helpers themselves.
    controller._selected_tags.add(tag_a)
    controller._selected_tags.add(tag_b)

    tag_a.mousePressEvent(_FakeEvent(scene_pos=QPointF(10.0, 0.0)))

    assert tag_a in controller._selected_tags
    assert tag_b in controller._selected_tags
    assert len(controller._selected_tags) == 2


def test_press_on_unselected_tag_without_modifier_collapses_to_one() -> None:
    """Plain LMB press on a tag that is NOT part of the current
    selection must replace the selection with just that tag.
    This is the dominant single-click-to-edit interaction and
    must not be regressed by the group-preservation logic."""
    _ensure_app()
    controller = _make_controller()
    tag_a = _make_tag_wired_to(controller, x=1.0)
    tag_b = _make_tag_wired_to(controller, x=2.0)
    tag_c = _make_tag_wired_to(controller, x=3.0)
    controller._selected_tags.add(tag_a)
    controller._selected_tags.add(tag_b)

    tag_c.mousePressEvent(_FakeEvent(scene_pos=QPointF(30.0, 0.0)))

    assert controller._selected_tags == {tag_c}


def test_notify_drag_started_after_in_group_press_snapshots_all() -> None:
    """End-to-end: after a plain press on a group member, the
    drag-origin snapshot taken by notify_drag_started must hold
    every selected tag's id — not just the pressed one. This is
    what makes the group-drag mirror viable."""
    _ensure_app()
    controller = _make_controller()
    tag_a = _make_tag_wired_to(controller, x=1.0)
    tag_b = _make_tag_wired_to(controller, x=2.0)
    controller._selected_tags.add(tag_a)
    controller._selected_tags.add(tag_b)

    # Press on tag_a (in the group). The press handler itself
    # calls notify_drag_started since tag_a.movable is True.
    tag_a.mousePressEvent(_FakeEvent(scene_pos=QPointF(10.0, 0.0)))

    assert controller._drag_anchor_tag is tag_a
    snapshot_ids = set(controller._drag_group_origin.keys())
    assert snapshot_ids == {id(tag_a), id(tag_b)}
    # Origins were recorded against each tag's current value.
    assert controller._drag_group_origin[id(tag_a)] == 1.0
    assert controller._drag_group_origin[id(tag_b)] == 2.0


def test_notify_drag_started_singleton_after_collapse() -> None:
    """Sanity check the inverse: a press on an unselected tag
    collapses to a singleton, so notify_drag_started records
    only that tag — there is no group to mirror."""
    _ensure_app()
    controller = _make_controller()
    tag_a = _make_tag_wired_to(controller, x=1.0)
    tag_b = _make_tag_wired_to(controller, x=2.0)
    tag_c = _make_tag_wired_to(controller, x=3.0)
    controller._selected_tags.add(tag_a)
    controller._selected_tags.add(tag_b)

    tag_c.mousePressEvent(_FakeEvent(scene_pos=QPointF(30.0, 0.0)))

    assert controller._drag_anchor_tag is tag_c
    assert set(controller._drag_group_origin.keys()) == {id(tag_c)}
