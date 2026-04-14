from __future__ import annotations

from typing import List


def solid_fill(led_count: int, rgb: List[int]) -> List[List[int]]:
    if led_count <= 0:
        return []
    return [[rgb[0], rgb[1], rgb[2]] for _ in range(led_count)]


def apply_fill_range(colors: List[List[int]], start: int, end: int, rgb: List[int]) -> List[List[int]]:
    """Fill inclusive LED range [start, end] with rgb and return updated colors copy."""
    updated = [list(color) for color in colors]
    if not updated:
        return updated

    left = max(0, min(start, end))
    right = min(len(updated) - 1, max(start, end))
    for i in range(left, right + 1):
        updated[i] = [rgb[0], rgb[1], rgb[2]]
    return updated
