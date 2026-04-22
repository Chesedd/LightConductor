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
    time_seconds: float,
    beat_times: Any,
    fallback_granularity: float,
    beat_tolerance: float = 0.05,
) -> float:
    """Snap time_seconds with magnetic-beat behavior.

    The fallback grid is always computed first as
    round(time_seconds / fallback_granularity) * fallback_granularity
    rounded to 6 decimals. When beat_times is empty or None the fallback
    is returned immediately. Otherwise the nearest element of beat_times
    is located via np.searchsorted (ties go to the earlier beat, values
    outside [beat_times[0], beat_times[-1]] fall to the boundary beat).
    If that nearest beat is within beat_tolerance seconds of time_seconds,
    the beat is returned; otherwise the grid-snapped fallback is used.
    Returns a plain float.
    """
    fallback_snap = round(time_seconds / fallback_granularity) * fallback_granularity
    fallback_snap = float(round(fallback_snap, 6))

    if beat_times is None or len(beat_times) == 0:
        return fallback_snap

    if time_seconds <= beat_times[0]:
        nearest_beat = float(beat_times[0])
    elif time_seconds >= beat_times[-1]:
        nearest_beat = float(beat_times[-1])
    else:
        idx = int(np.searchsorted(beat_times, time_seconds))
        left = float(beat_times[idx - 1])
        right = float(beat_times[idx])
        if (time_seconds - left) <= (right - time_seconds):
            nearest_beat = left
        else:
            nearest_beat = right

    if abs(time_seconds - nearest_beat) <= beat_tolerance:
        return nearest_beat
    return fallback_snap
