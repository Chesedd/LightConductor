"""Pure helper for applying mouse-wheel zoom to the per-cell side
length used by LedWireDialog and TagPinsDialog.

A single wheel tick multiplies (zoom in) or divides (zoom out) the
current cell side by ``step`` (default ×1.15, so ~×2 after 5 ticks),
clamps the result to ``[min_size, max_size]``, and guarantees a
monotonic ±1 step so repeated ticks near the clamp edges still
progress rather than getting stuck on ``int()`` truncation.

The dialog is expected to map a Qt ``QWheelEvent.angleDelta().y()``
(multiples of 120 per tick) onto ``wheel_delta`` — the helper only
looks at the sign.
"""

from __future__ import annotations

DEFAULT_MIN_CELL = 6
DEFAULT_MAX_CELL = 64
DEFAULT_STEP = 1.15


def apply_wheel_zoom(
    current_cell_size: int,
    wheel_delta: int,
    *,
    min_size: int = DEFAULT_MIN_CELL,
    max_size: int = DEFAULT_MAX_CELL,
    step: float = DEFAULT_STEP,
) -> int:
    """Return a new cell side for one wheel tick.

    ``wheel_delta > 0`` zooms in (multiply by ``step``), ``< 0`` zooms
    out (divide by ``step``). ``wheel_delta == 0`` returns the input
    unchanged. The result is always an int inside ``[min_size,
    max_size]``.

    To avoid getting stuck on ``int()`` truncation near small sizes
    (e.g. ``int(6 * 1.15) == 6``), a minimum ±1 progression is
    enforced before clamping.

    Examples:
        >>> apply_wheel_zoom(16, 120)
        18
        >>> apply_wheel_zoom(16, -120)
        13
        >>> apply_wheel_zoom(16, 0)
        16
        >>> apply_wheel_zoom(64, 120)
        64
        >>> apply_wheel_zoom(6, -120)
        6
        >>> apply_wheel_zoom(60, 120)
        64
    """
    if wheel_delta == 0:
        return current_cell_size
    if wheel_delta > 0:
        new_size = int(current_cell_size * step)
        if new_size <= current_cell_size:
            new_size = current_cell_size + 1
    else:
        new_size = int(current_cell_size / step)
        if new_size >= current_cell_size:
            new_size = current_cell_size - 1
    return max(min_size, min(max_size, new_size))
