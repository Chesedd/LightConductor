"""Pure LED-strip preview renderer. Given a domain Slave and a time
in seconds, computes the RGB buffer the physical strip would display.
No Qt, no widget dependencies, no I/O. Consumed by LedStripView (UI)
and later by 4.1 live preview."""

from __future__ import annotations

import bisect
from typing import List, Tuple

from lightconductor.domain.models import Slave


def _safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _action_is_on(action) -> bool:
    # Mirrors CompileShowsForMastersUseCase._action_is_on semantics.
    # Keep in sync if that changes.
    if isinstance(action, bool):
        return action
    if isinstance(action, str):
        return action.strip().lower() in {"on", "true", "1", "yes"}
    return bool(action)


def _normalize_color(color_like) -> Tuple[int, int, int]:
    # Mirrors CompileShowsForMastersUseCase._normalize_color.
    if isinstance(color_like, str):
        parts = [p.strip() for p in color_like.split(",")]
        if len(parts) == 3:
            try:
                return tuple(max(0, min(255, int(p))) for p in parts)
            except ValueError:
                pass
        return (0, 0, 0)
    if isinstance(color_like, (list, tuple)) and len(color_like) >= 3:
        try:
            return (
                max(0, min(255, int(color_like[0]))),
                max(0, min(255, int(color_like[1]))),
                max(0, min(255, int(color_like[2]))),
            )
        except (TypeError, ValueError):
            return (0, 0, 0)
    return (0, 0, 0)


def render_led_strip_at(
    slave: Slave, time_seconds: float,
) -> List[Tuple[int, int, int]]:
    """Compute RGB buffer of length slave.led_count at the given time.
    Returns an empty list when led_count <= 0. Tag types are processed
    in ascending int(pin) order; overlapping topologies resolve
    last-wins. Out-of-range topology indices are silently skipped."""

    led_count = _safe_int(getattr(slave, "led_count", 0) or 0)
    if led_count <= 0:
        return []
    buffer: List[Tuple[int, int, int]] = [(0, 0, 0)] * led_count

    tag_types = sorted(
        slave.tag_types.values(),
        key=lambda tt: _safe_int(getattr(tt, "pin", 0)),
    )
    for tag_type in tag_types:
        tags = getattr(tag_type, "tags", None) or []
        if not tags:
            continue
        times = [float(t.time_seconds) for t in tags]
        idx = bisect.bisect_right(times, float(time_seconds)) - 1
        if idx < 0:
            continue
        active = tags[idx]
        if not _action_is_on(active.action):
            continue
        topology = list(getattr(tag_type, "topology", []) or [])
        colors = getattr(active, "colors", None) or []
        for i, phys_idx in enumerate(topology):
            color_like = colors[i] if i < len(colors) else (0, 0, 0)
            color = _normalize_color(color_like)
            if 0 <= phys_idx < led_count:
                buffer[phys_idx] = color
    return buffer
