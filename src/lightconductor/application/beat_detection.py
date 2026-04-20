"""Pure beat-detection and snap utilities. No Qt, no widget dependencies.
Consumed by WaveRenderer (storage) and later by TagTimelineController (snap).
"""

from __future__ import annotations

from typing import Any

import librosa
import numpy as np


def detect_beats(audio: Any, sr: Any) -> Any:
    """Return a 1-D numpy float array of beat onset times in seconds.

    Returns np.empty(0, dtype=float) when audio is None, empty, or sr falsy.
    Wraps librosa.beat.beat_track with units="time". On any librosa failure
    (ParameterError, RuntimeError, ValueError) returns np.empty(0, dtype=float).
    Does NOT raise.
    """
    if audio is None or not sr:
        return np.empty(0, dtype=float)
    if not hasattr(audio, "__len__") or len(audio) == 0:
        return np.empty(0, dtype=float)

    try:
        _tempo, beats = librosa.beat.beat_track(y=audio, sr=sr, units="time")
    except (librosa.ParameterError, RuntimeError, ValueError):
        return np.empty(0, dtype=float)

    return np.asarray(beats, dtype=float)


def snap_to_nearest_beat(
    time_seconds: float, beat_times: Any, fallback_granularity: float
) -> float:
    """Snap time_seconds to the nearest element of beat_times.

    If beat_times is empty or None, fall back to
    round(time_seconds / fallback_granularity) * fallback_granularity
    rounded to 6 decimals. Otherwise uses np.searchsorted to pick the closer
    of the two neighbors (ties go to the earlier beat). Handles
    time_seconds below beat_times[0] and above beat_times[-1].
    Returns a plain float.
    """
    if beat_times is None or len(beat_times) == 0:
        snapped = round(time_seconds / fallback_granularity) * fallback_granularity
        return float(round(snapped, 6))

    if time_seconds <= beat_times[0]:
        return float(beat_times[0])
    if time_seconds >= beat_times[-1]:
        return float(beat_times[-1])

    idx = int(np.searchsorted(beat_times, time_seconds))
    left = float(beat_times[idx - 1])
    right = float(beat_times[idx])
    if (time_seconds - left) <= (right - time_seconds):
        return left
    return right
