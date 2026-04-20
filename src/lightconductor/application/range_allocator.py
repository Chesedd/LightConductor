from __future__ import annotations

from typing import Iterable, List, Tuple


def available_starts(
    led_count: int, occupied_ranges: Iterable[Tuple[int, int]], length: int
) -> List[int]:
    if led_count <= 0 or length <= 0 or length > led_count:
        return []

    occupied = set()
    for start, size in occupied_ranges:
        for led in range(max(0, start), max(0, start) + max(0, size)):
            occupied.add(led)

    starts: List[int] = []
    for start in range(0, led_count - length + 1):
        candidate = range(start, start + length)
        if all(led not in occupied for led in candidate):
            starts.append(start)
    return starts
