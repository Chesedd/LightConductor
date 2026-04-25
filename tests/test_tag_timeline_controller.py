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


def test_drag_snap_lands_on_002_grid_when_no_nearby_beat() -> None:
    """Simulates a drag finish when beats exist but none are within the
    0.05 tolerance of the drop point: the tag should land on the 0.02
    grid, not on the distant beat."""
    beats = np.array([1.0, 2.0], dtype=float)
    # 1.5 is 0.5 from the nearest beat, well outside 0.05 tolerance.
    snapped = snap_to_nearest_beat(1.5, beats, SNAP_GRANULARITY_SECONDS)
    assert snapped == 1.5


def test_drag_snap_magnetizes_to_beat_within_tolerance() -> None:
    """Simulates a drag finish that drops within 0.05 s of a beat: the
    tag should magnetize to the beat rather than the 0.02 grid."""
    beats = np.array([1.0, 2.0], dtype=float)
    # 1.03 is 0.03 from beat 1.0 (within default 0.05 tolerance).
    snapped = snap_to_nearest_beat(1.03, beats, SNAP_GRANULARITY_SECONDS)
    assert snapped == 1.0
