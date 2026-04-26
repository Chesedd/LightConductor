"""Tests for the click-vs-drag dispatch helper used by
ProjectScreen.TagLogic.TagObject.Tag.mouseReleaseEvent.

The helper `_is_click_release` lives at module level so tests
can exercise the dispatch logic without an event loop. The
production handler delegates to it; this file pins the
threshold semantics (4 px / 0.30 s) and the modifier-press
short-circuit.
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

import pytest  # noqa: E402

pytest.importorskip("PyQt6")

from ProjectScreen.TagLogic.TagObject import (  # noqa: E402
    CLICK_PIXEL_THRESHOLD,
    CLICK_TIME_THRESHOLD_S,
    _is_click_release,
)


def _call(
    *,
    press_x: float | None = 100.0,
    press_y: float | None = 50.0,
    release_x: float = 100.0,
    release_y: float = 50.0,
    press_t: float | None = 1000.0,
    release_t: float = 1000.05,
    was_extend: bool = False,
) -> bool:
    return _is_click_release(
        press_pos_x=press_x,
        press_pos_y=press_y,
        release_pos_x=release_x,
        release_pos_y=release_y,
        press_monotonic=press_t,
        release_monotonic=release_t,
        was_extend=was_extend,
    )


def test_click_no_move_short_duration_returns_true() -> None:
    assert _call() is True


def test_drag_large_move_returns_false() -> None:
    # dx = 10, dy = 0 — well above the 4 px click threshold.
    assert _call(release_x=110.0) is False


def test_long_press_no_move_returns_false() -> None:
    # No motion but elapsed = 0.5s > 0.30s threshold.
    assert _call(release_t=1000.5) is False


def test_extend_modifier_returns_false() -> None:
    # Modifier-press is selection-only; never a click.
    assert _call(was_extend=True) is False
    # Even a perfect zero-motion zero-duration release with
    # modifier still must not open the dialog.
    assert (
        _call(
            release_x=100.0,
            release_y=50.0,
            release_t=1000.0,
            was_extend=True,
        )
        is False
    )


def test_missing_press_state_returns_false() -> None:
    # press_pos_x is None (no matching press): no-op release.
    assert _call(press_x=None) is False
    assert _call(press_y=None) is False
    assert _call(press_t=None) is False


def test_threshold_boundary_pixel() -> None:
    # Exactly at the 4 px threshold → still a click.
    assert _call(release_x=100.0 + CLICK_PIXEL_THRESHOLD) is True
    # Just over the threshold → drag.
    assert _call(release_x=100.0 + CLICK_PIXEL_THRESHOLD + 0.01) is False


def test_threshold_boundary_time() -> None:
    # Exactly at the 0.30 s threshold → still a click.
    assert _call(release_t=1000.0 + CLICK_TIME_THRESHOLD_S) is True
    # Just over the threshold → drag.
    assert _call(release_t=1000.0 + CLICK_TIME_THRESHOLD_S + 0.001) is False


def test_diagonal_move_within_threshold() -> None:
    # 3-4-5 triangle: dx=3, dy=4 → moved=5 → over 4 px → drag.
    assert _call(release_x=103.0, release_y=54.0) is False
    # dx=2, dy=2 → moved≈2.83 → under 4 px → click.
    assert _call(release_x=102.0, release_y=52.0) is True
