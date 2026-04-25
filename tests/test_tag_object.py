"""Tests for ProjectScreen.TagLogic.TagObject.

Phase 15.1 bug: at 0.02s grid spacing, the bounding rects of
neighboring tags overlap any single click point. Because
Tag.mousePressEvent did not accept the event, Qt's default
propagation delivered the same click to every tag under the cursor
— each one opened its own TagPinsDialog. The fix is to call
event.accept() at the end of mousePressEvent so the event stops at
the topmost tag.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from ProjectScreen.TagLogic.TagObject import Tag  # noqa: E402

_app: QApplication | None = None


def _ensure_app() -> QApplication:
    global _app
    existing = QApplication.instance()
    if existing is not None:
        return existing  # type: ignore[return-value]
    _app = QApplication([])
    return _app


class _FakeEvent:
    """Minimal stand-in for a QGraphicsSceneMouseEvent.

    Tag.mousePressEvent only calls event.accept() on it — the
    base InfiniteLine.mousePressEvent is inherited from
    QGraphicsObject which tolerates plain accept/ignore stubs in
    headless tests.
    """

    def __init__(self) -> None:
        self._accepted = False

    def accept(self) -> None:
        self._accepted = True

    def ignore(self) -> None:
        self._accepted = False

    def isAccepted(self) -> bool:
        return self._accepted


def _make_tag() -> Tag:
    return Tag(pos=QPointF(0.5, 0.0), manager=None)


def test_mouse_press_accepts_event_with_no_manager() -> None:
    _ensure_app()
    tag = _make_tag()
    event = _FakeEvent()
    tag.mousePressEvent(event)
    assert event.isAccepted() is True


def test_mouse_press_accepts_event_with_manager_and_project_window() -> None:
    """Even when openTagEditWindow is invoked, the event must be
    accepted so the click does not propagate to a second tag
    whose bounding rect overlaps at 0.02s spacing."""
    _ensure_app()

    opened: list[Any] = []

    project_window = SimpleNamespace(
        openTagEditWindow=lambda tag: opened.append(tag),
    )
    manager = SimpleNamespace(
        box=None,
        _project_window=project_window,
    )

    tag = Tag(pos=QPointF(0.5, 0.0), manager=manager)
    event = _FakeEvent()
    tag.mousePressEvent(event)

    assert event.isAccepted() is True
    assert opened == [tag]
