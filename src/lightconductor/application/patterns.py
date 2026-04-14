from __future__ import annotations

from typing import List


def solid_fill(led_count: int, rgb: List[int]) -> List[List[int]]:
    if led_count <= 0:
        return []
    return [[rgb[0], rgb[1], rgb[2]] for _ in range(led_count)]
