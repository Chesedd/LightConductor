"""Tests for ProjectScreen.TagLogic.WaveRenderer.

Focused on the playhead click-to-seek path. The renderer's onClick
snaps the mouse x-coordinate to the SNAP_GRANULARITY_SECONDS grid
(shared with Phase 14 tag placement) before issuing the
QMediaPlayer.setPosition call. Prior to Phase 15.1, the code
hardcoded round(x, 1) — a 0.1s grid that did not match the 0.02s
placement grid. These tests lock in the unified snap.

The renderer is heavy to instantiate (QMediaPlayer, librosa,
beat detection). We skip __init__ via __new__ and attach only the
attributes that onClick touches. This keeps the tests fast and
avoids pulling in audio backends on CI.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtCore import QPointF, QRectF  # noqa: E402

from ProjectScreen.TagLogic.TagTimelineController import (  # noqa: E402
    SNAP_GRANULARITY_SECONDS,
)
from ProjectScreen.TagLogic.WaveRenderer import WaveRenderer  # noqa: E402


class _FakeViewBox:
    def __init__(self, x_val: float) -> None:
        self._x = x_val

    def mapSceneToView(self, pos: QPointF) -> QPointF:
        return QPointF(self._x, 0.0)


class _FakePlotWidget:
    def sceneBoundingRect(self) -> QRectF:
        return QRectF(0.0, 0.0, 1000.0, 200.0)


class _FakePlayer:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def setPosition(self, ms: int) -> None:
        self.calls.append(ms)


class _FakeEvent:
    def __init__(self, pos: QPointF) -> None:
        self._pos = pos

    def scenePos(self) -> QPointF:
        return self._pos


def _make_renderer(view_x: float) -> WaveRenderer:
    renderer = WaveRenderer.__new__(WaveRenderer)
    renderer._plot_widget = _FakePlotWidget()
    renderer.vb = _FakeViewBox(view_x)
    renderer.audioPlayer = _FakePlayer()
    return renderer


def test_on_click_on_grid_seeks_to_exact_millis() -> None:
    assert SNAP_GRANULARITY_SECONDS == 0.02
    renderer = _make_renderer(1.0)
    renderer.onClick(_FakeEvent(QPointF(50.0, 50.0)))
    assert renderer.audioPlayer.calls == [1000]


def test_on_click_rounds_down_to_nearest_002_grid_point() -> None:
    # 1.013 is 0.007 from 1.02 and 0.013 from 1.00 → snaps up to 1.02.
    renderer = _make_renderer(1.013)
    renderer.onClick(_FakeEvent(QPointF(50.0, 50.0)))
    assert renderer.audioPlayer.calls == [1020]


def test_on_click_rounds_up_to_nearest_002_grid_point() -> None:
    # 1.057 is 0.003 from 1.06 and 0.017 from 1.04 → snaps up to 1.06.
    renderer = _make_renderer(1.057)
    renderer.onClick(_FakeEvent(QPointF(50.0, 50.0)))
    assert renderer.audioPlayer.calls == [1060]


def test_on_click_negative_x_clamps_to_zero() -> None:
    # mapSceneToView can land slightly before t=0 near the left edge.
    # The previous round(x, 1) path could feed a negative ms to
    # QMediaPlayer; clamp defensively at the snap step.
    renderer = _make_renderer(-0.05)
    renderer.onClick(_FakeEvent(QPointF(0.0, 50.0)))
    assert renderer.audioPlayer.calls == [0]


def test_on_click_outside_scene_bounding_rect_is_ignored() -> None:
    renderer = _make_renderer(1.0)

    class _NeverContainsRect:
        def contains(self, _pos: QPointF) -> bool:
            return False

    class _PlotOutside:
        def sceneBoundingRect(self) -> _NeverContainsRect:
            return _NeverContainsRect()

    renderer._plot_widget = _PlotOutside()
    renderer.onClick(_FakeEvent(QPointF(0.0, 0.0)))
    assert renderer.audioPlayer.calls == []
