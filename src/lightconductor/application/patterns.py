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


def sequential_fill_frames(led_count: int, rgb: List[int]) -> List[List[List[int]]]:
    if led_count <= 0:
        return []
    off = [0, 0, 0]
    frames: List[List[List[int]]] = []
    for lit_count in range(1, led_count + 1):
        frame = [list(rgb) if i < lit_count else list(off) for i in range(led_count)]
        frames.append(frame)
    return frames


def moving_window_frames(led_count: int, window_size: int, rgb: List[int]) -> List[List[List[int]]]:
    if led_count <= 0:
        return []
    if window_size <= 0:
        window_size = 1
    window_size = min(window_size, led_count)
    off = [0, 0, 0]
    frames: List[List[List[int]]] = []
    for start in range(0, led_count - window_size + 1):
        frame = [list(off) for _ in range(led_count)]
        for i in range(start, start + window_size):
            frame[i] = list(rgb)
        frames.append(frame)
    return frames


def floating_gradient_frames(led_count: int, rgb: List[int], width: int = 4) -> List[List[List[int]]]:
    if led_count <= 0:
        return []
    if width <= 0:
        width = 1
    frames: List[List[List[int]]] = []
    for center in range(led_count):
        frame: List[List[int]] = []
        for led in range(led_count):
            distance = abs(led - center)
            intensity = max(0.0, 1.0 - (distance / width))
            frame.append([
                int(rgb[0] * intensity),
                int(rgb[1] * intensity),
                int(rgb[2] * intensity),
            ])
        frames.append(frame)
    return frames


def build_timed_pattern_tags(
    frames: List[List[List[int]]],
    start_time: float,
    end_time: float,
    step: float,
) -> List[dict]:
    if not frames or step <= 0 or end_time < start_time:
        return []
    tags: List[dict] = []
    t = start_time
    frame_index = 0
    while t <= end_time + 1e-9:
        tags.append({
            "time": round(t, 3),
            "action": True,
            "colors": frames[frame_index % len(frames)],
        })
        frame_index += 1
        t += step
    return tags
