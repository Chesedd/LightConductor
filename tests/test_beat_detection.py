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
    beats = np.array([2.5], dtype=float)
    assert snap_to_nearest_beat(0.0, beats, 0.1) == 2.5
    assert snap_to_nearest_beat(2.5, beats, 0.1) == 2.5
    assert snap_to_nearest_beat(100.0, beats, 0.1) == 2.5


def test_snap_multiple_beats_picks_nearest():
    beats = np.array([1.0, 2.0, 3.0], dtype=float)
    assert snap_to_nearest_beat(1.4, beats, 0.1) == 1.0
    assert snap_to_nearest_beat(1.6, beats, 0.1) == 2.0
    # Tie goes to the earlier beat.
    assert snap_to_nearest_beat(1.5, beats, 0.1) == 1.0
    assert snap_to_nearest_beat(2.9, beats, 0.1) == 3.0
    # Above last and below first clamp to the edges.
    assert snap_to_nearest_beat(5.0, beats, 0.1) == 3.0
    assert snap_to_nearest_beat(-1.0, beats, 0.1) == 1.0


def test_snap_fallback_granularity_0_25():
    empty = np.empty(0, dtype=float)
    assert snap_to_nearest_beat(0.3, empty, 0.25) == 0.25
    assert snap_to_nearest_beat(0.4, empty, 0.25) == 0.5


def test_snap_return_type_is_plain_float():
    # Fallback branch.
    result_fallback = snap_to_nearest_beat(0.37, None, 0.1)
    assert isinstance(result_fallback, float)
    assert not isinstance(result_fallback, np.floating)

    # Beat-match branch.
    beats = np.array([1.0, 2.0, 3.0], dtype=float)
    result_match = snap_to_nearest_beat(1.4, beats, 0.1)
    assert isinstance(result_match, float)
    assert not isinstance(result_match, np.floating)

    # Clamp branch (above last).
    result_clamp = snap_to_nearest_beat(100.0, beats, 0.1)
    assert isinstance(result_clamp, float)
    assert not isinstance(result_clamp, np.floating)


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
