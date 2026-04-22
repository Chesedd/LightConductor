"""Tests for ProjectScreen.TagLogic.TagTimelineController.

Exercises the module-level snap granularity constant and confirms
that the snap_to_nearest_beat fallback path lands on 0.02-multiples
when configured with the controller's constant. The controller class
itself is heavily Qt-coupled and is exercised via integration tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np

from lightconductor.application.beat_detection import snap_to_nearest_beat
from ProjectScreen.TagLogic.TagTimelineController import (
    SNAP_GRANULARITY_SECONDS,
)


def test_snap_granularity_constant_value() -> None:
    assert SNAP_GRANULARITY_SECONDS == 0.02


def test_drag_snap_uses_002_grid_in_fallback() -> None:
    empty = np.empty(0, dtype=float)
    # 1.31 is off-grid; 0.02 step → snaps to 1.32 (banker's rounding).
    assert snap_to_nearest_beat(1.31, empty, SNAP_GRANULARITY_SECONDS) == 1.32
    # 1.30 is exactly on-grid (65 * 0.02).
    assert snap_to_nearest_beat(1.30, empty, SNAP_GRANULARITY_SECONDS) == 1.30
    # 0.0 is on-grid trivially.
    assert snap_to_nearest_beat(0.0, empty, SNAP_GRANULARITY_SECONDS) == 0.0
