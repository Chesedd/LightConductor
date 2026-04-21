"""Pure LED canvas preview renderer. Given a domain Slave and a
time in seconds, computes the RGB buffer the canvas grid would
display. No Qt, no widget dependencies, no I/O. Consumed by
LedGridView (UI) and later by 4.1 live preview.

The returned buffer has one entry per canvas cell
(`grid_rows * grid_columns`), not per physical LED. Callers that
need wire-space ordering should translate via
`cell_to_wire_index`.
"""

from __future__ import annotations

import bisect
from typing import Any, List, Optional, Tuple

from lightconductor.domain.models import Slave


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _action_is_on(action: Any) -> bool:
    # Mirrors CompileShowsForMastersUseCase._action_is_on semantics.
    # Keep in sync if that changes.
    if isinstance(action, bool):
        return action
    if isinstance(action, str):
        return action.strip().lower() in {"on", "true", "1", "yes"}
    return bool(action)


def _normalize_color(color_like: Any) -> Tuple[int, int, int]:
    # Mirrors CompileShowsForMastersUseCase._normalize_color.
    if isinstance(color_like, str):
        parts = [p.strip() for p in color_like.split(",")]
        if len(parts) == 3:
            try:
                return tuple(max(0, min(255, int(p))) for p in parts)  # type: ignore[return-value]
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


def cell_to_wire_index(slave: Slave, cell: int) -> Optional[int]:
    """Return the wire position of the given canvas cell, or
    None if the cell has no physical LED (not present in
    `slave.led_cells`). O(N) lookup."""
    led_cells = list(getattr(slave, "led_cells", []) or [])
    try:
        return led_cells.index(int(cell))
    except (TypeError, ValueError):
        return None


def _canvas_size(slave: Slave) -> int:
    rows = _safe_int(getattr(slave, "grid_rows", 0))
    cols = _safe_int(getattr(slave, "grid_columns", 0))
    return max(0, rows * cols)


def _render_buffer(
    slave: Slave,
    time_seconds: float,
    skip_type_name: str | None = None,
) -> List[Tuple[int, int, int]]:
    canvas_size = _canvas_size(slave)
    if canvas_size <= 0:
        return []
    buffer: List[Tuple[int, int, int]] = [(0, 0, 0)] * canvas_size

    tag_types = sorted(
        slave.tag_types.values(),
        key=lambda tt: _safe_int(getattr(tt, "pin", 0)),
    )
    for tag_type in tag_types:
        if (
            skip_type_name is not None
            and getattr(tag_type, "name", None) == skip_type_name
        ):
            continue
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
        for i, cell_idx in enumerate(topology):
            color_like = colors[i] if i < len(colors) else (0, 0, 0)
            color = _normalize_color(color_like)
            if 0 <= cell_idx < canvas_size:
                buffer[cell_idx] = color
    return buffer


def render_canvas_at(
    slave: Slave,
    time_seconds: float,
) -> List[Tuple[int, int, int]]:
    """Compute RGB buffer of length `grid_rows * grid_columns`
    at the given time. Returns an empty list when canvas size
    <= 0. Tag types are processed in ascending int(pin) order;
    overlapping topologies resolve last-wins. Cells outside the
    canvas are silently skipped. Cells inside the canvas but not
    in `led_cells` still show their color for UI preview; the
    firmware-facing compile path filters those separately."""

    return _render_buffer(slave, time_seconds)


def render_canvas_with_overlay(
    slave: Slave,
    time_seconds: float,
    overlay_type_name: str,
    overlay_colors: Any,
    overlay_action: Any,
) -> List[Tuple[int, int, int]]:
    """Render slave state at `time_seconds`, then overlay a
    hypothetical tag of type `overlay_type_name` whose
    (colors, action) the caller is currently editing (e.g. in
    TagPinsDialog). Matches the semantics the user would see after
    committing the tag and leaving the cursor at T.

    If canvas size <= 0, returns []. If the slave does not
    contain a tag type named `overlay_type_name`, returns the
    base buffer from `render_canvas_at` (no overlay applied).
    Otherwise, the baseline is computed skipping
    `overlay_type_name`, then the overlay is applied honoring
    `overlay_action`. Returned buffer has length
    `grid_rows * grid_columns`."""

    canvas_size = _canvas_size(slave)
    if canvas_size <= 0:
        return []

    tag_types = getattr(slave, "tag_types", {}) or {}
    overlay_type = tag_types.get(overlay_type_name)
    if overlay_type is None:
        return _render_buffer(slave, time_seconds)

    buffer = _render_buffer(slave, time_seconds, skip_type_name=overlay_type_name)
    topology = list(getattr(overlay_type, "topology", []) or [])

    if not _action_is_on(overlay_action):
        for cell_idx in topology:
            if 0 <= cell_idx < canvas_size:
                buffer[cell_idx] = (0, 0, 0)
        return buffer

    colors = list(overlay_colors or [])
    for i, cell_idx in enumerate(topology):
        color_like = colors[i] if i < len(colors) else (0, 0, 0)
        color = _normalize_color(color_like)
        if 0 <= cell_idx < canvas_size:
            buffer[cell_idx] = color
    return buffer
