import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np

from lightconductor.application.beat_detection import (
    detect_beats,
    snap_to_nearest_beat,
)

# ---------------------------------------------------------------------------
# snap_to_nearest_beat
# ---------------------------------------------------------------------------


def test_snap_fallback_empty_beats_granularity_0_1():
    empty = np.empty(0, dtype=float)
    assert snap_to_nearest_beat(0.37, empty, 0.1) == 0.4
    assert snap_to_nearest_beat(0.33, empty, 0.1) == 0.3
    assert snap_to_nearest_beat(0.0, empty, 0.1) == 0.0


def test_snap_fallback_none_beats_matches_empty():
    assert snap_to_nearest_beat(0.37, None, 0.1) == 0.4
    assert snap_to_nearest_beat(0.33, None, 0.1) == 0.3
    assert snap_to_nearest_beat(0.0, None, 0.1) == 0.0


def test_snap_single_beat_always_returns_it():
    # With an infinite tolerance, the nearest beat always wins.
    beats = np.array([2.5], dtype=float)
    inf = float("inf")
    assert snap_to_nearest_beat(0.0, beats, 0.1, beat_tolerance=inf) == 2.5
    assert snap_to_nearest_beat(2.5, beats, 0.1, beat_tolerance=inf) == 2.5
    assert snap_to_nearest_beat(100.0, beats, 0.1, beat_tolerance=inf) == 2.5


def test_snap_multiple_beats_picks_nearest():
    # With an infinite tolerance the nearest-beat selection rules are
    # exercised exactly as before the magnetic-tolerance change.
    beats = np.array([1.0, 2.0, 3.0], dtype=float)
    inf = float("inf")
    assert snap_to_nearest_beat(1.4, beats, 0.1, beat_tolerance=inf) == 1.0
    assert snap_to_nearest_beat(1.6, beats, 0.1, beat_tolerance=inf) == 2.0
    # Tie goes to the earlier beat.
    assert snap_to_nearest_beat(1.5, beats, 0.1, beat_tolerance=inf) == 1.0
    assert snap_to_nearest_beat(2.9, beats, 0.1, beat_tolerance=inf) == 3.0
    # Above last and below first clamp to the edges.
    assert snap_to_nearest_beat(5.0, beats, 0.1, beat_tolerance=inf) == 3.0
    assert snap_to_nearest_beat(-1.0, beats, 0.1, beat_tolerance=inf) == 1.0


def test_snap_fallback_granularity_0_25():
    empty = np.empty(0, dtype=float)
    assert snap_to_nearest_beat(0.3, empty, 0.25) == 0.25
    assert snap_to_nearest_beat(0.4, empty, 0.25) == 0.5


def test_snap_return_type_is_plain_float():
    # Fallback branch.
    result_fallback = snap_to_nearest_beat(0.37, None, 0.1)
    assert isinstance(result_fallback, float)
    assert not isinstance(result_fallback, np.floating)

    # Beat-match branch (requires tolerance large enough to pick the beat).
    beats = np.array([1.0, 2.0, 3.0], dtype=float)
    result_match = snap_to_nearest_beat(1.4, beats, 0.1, beat_tolerance=1.0)
    assert isinstance(result_match, float)
    assert not isinstance(result_match, np.floating)

    # Clamp branch (above last) still returns a plain float when the
    # boundary beat is within tolerance.
    result_clamp = snap_to_nearest_beat(100.0, beats, 0.1, beat_tolerance=float("inf"))
    assert isinstance(result_clamp, float)
    assert not isinstance(result_clamp, np.floating)


# ---------------------------------------------------------------------------
# snap_to_nearest_beat: magnetic-tolerance behavior (default beat_tolerance)
# ---------------------------------------------------------------------------


def test_snap_within_tolerance_snaps_to_beat():
    beats = np.array([1.0, 2.0], dtype=float)
    # 1.03 is 0.03 away from the nearest beat (1.0), within the default
    # 0.05 tolerance -> snap to the beat.
    assert snap_to_nearest_beat(1.03, beats, 0.02) == 1.0


def test_snap_outside_tolerance_uses_fallback_grid():
    beats = np.array([1.0, 2.0], dtype=float)
    # 1.10 is 0.10 away from the nearest beat, outside the default 0.05
    # tolerance -> fall back to the 0.02 grid (1.10 is already on grid).
    assert snap_to_nearest_beat(1.10, beats, 0.02) == 1.10


def test_snap_between_beats_uses_fallback_grid():
    beats = np.array([1.0, 2.0], dtype=float)
    # 1.5 is 0.5 from both beats, neither within tolerance -> fallback grid.
    assert snap_to_nearest_beat(1.5, beats, 0.02) == 1.5


def test_snap_below_first_beat_within_tolerance_snaps_to_it():
    beats = np.array([1.0, 2.0], dtype=float)
    # 0.97 is 0.03 below the first beat, within tolerance -> snap to 1.0.
    assert snap_to_nearest_beat(0.97, beats, 0.02) == 1.0


def test_snap_below_first_beat_outside_tolerance_uses_grid():
    beats = np.array([1.0, 2.0], dtype=float)
    # 0.5 is 0.5 below the first beat, far outside tolerance -> grid snap.
    assert snap_to_nearest_beat(0.5, beats, 0.02) == 0.5


def test_snap_empty_beats_ignores_tolerance():
    empty = np.empty(0, dtype=float)
    # Tolerance has no effect when there are no beats; always grid snap.
    assert snap_to_nearest_beat(0.38, empty, 0.02, beat_tolerance=0.0) == 0.38
    assert snap_to_nearest_beat(0.38, empty, 0.02, beat_tolerance=100.0) == 0.38


def test_snap_zero_tolerance_never_snaps_to_beat():
    beats = np.array([1.0, 2.0], dtype=float)
    # With tolerance=0, only exact-beat times land on a beat; everything
    # else goes to the fallback grid.
    assert snap_to_nearest_beat(1.0, beats, 0.02, beat_tolerance=0.0) == 1.0
    assert snap_to_nearest_beat(1.04, beats, 0.02, beat_tolerance=0.0) == 1.04
    assert snap_to_nearest_beat(1.5, beats, 0.02, beat_tolerance=0.0) == 1.5


# ---------------------------------------------------------------------------
# detect_beats
# ---------------------------------------------------------------------------


def test_detect_beats_none_audio_returns_empty():
    result = detect_beats(None, 22050)
    assert isinstance(result, np.ndarray)
    assert result.size == 0


def test_detect_beats_zero_length_audio_returns_empty():
    result = detect_beats(np.zeros(0, dtype=np.float32), 22050)
    assert isinstance(result, np.ndarray)
    assert result.size == 0


def test_detect_beats_zero_sr_returns_empty():
    audio = np.zeros(22050, dtype=np.float32)
    result = detect_beats(audio, 0)
    assert isinstance(result, np.ndarray)
    assert result.size == 0


def test_detect_beats_none_sr_returns_empty():
    audio = np.zeros(22050, dtype=np.float32)
    result = detect_beats(audio, None)
    assert isinstance(result, np.ndarray)
    assert result.size == 0


def test_detect_beats_synthetic_click_track():
    sr = 22050
    duration_s = 10.0
    audio = np.zeros(int(sr * duration_s), dtype=np.float32)

    impulse_samples = max(1, int(sr * 0.001))  # 1 ms impulse
    # 19 clicks at 0.5, 1.0, ..., 9.5 seconds.
    for i in range(1, 20):
        start = int(i * 0.5 * sr)
        end = start + impulse_samples
        audio[start:end] = 1.0

    result = detect_beats(audio, sr)

    assert isinstance(result, np.ndarray)
    assert np.issubdtype(result.dtype, np.floating)
    assert 10 <= len(result) <= 30
    assert np.all(np.diff(result) >= 0)
