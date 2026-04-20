"""Pattern generation service.

Facade over pure pattern functions in `application.patterns`.
Provides a single injection point for UI consumers and an
event-based API (`PatternEvent`) that complements the legacy
frame-based API for future timeline-centric refactors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from lightconductor.application.patterns import (
    apply_fill_range,
    build_timed_pattern_tags,
    floating_gradient_frames,
    moving_window_frames,
    sequential_fill_frames,
    solid_fill,
)


@dataclass(slots=True, frozen=True)
class PatternEvent:
    """A single (led_index, color, time) pattern event.

    `color` is a 3-element RGB list. The event is atomic:
    at `time_seconds`, LED `led_index` becomes `color`.
    """

    led_index: int
    color: List[int]
    time_seconds: float


class PatternService:
    """Stateless facade over pattern functions.

    Thin delegation to `application.patterns`; no I/O, no Qt.
    """

    def solid_fill(self, led_count: int, rgb: List[int]) -> List[List[int]]:
        return solid_fill(led_count, rgb)

    def apply_fill_range(
        self,
        colors: List[List[int]],
        start: int,
        end: int,
        rgb: List[int],
    ) -> List[List[int]]:
        return apply_fill_range(colors, start, end, rgb)

    def sequential_fill(self, led_count: int, rgb: List[int]) -> List[List[List[int]]]:
        return sequential_fill_frames(led_count, rgb)

    def moving_window(
        self, led_count: int, window_size: int, rgb: List[int]
    ) -> List[List[List[int]]]:
        return moving_window_frames(led_count, window_size, rgb)

    def floating_gradient(
        self, led_count: int, rgb: List[int], width: int = 4
    ) -> List[List[List[int]]]:
        return floating_gradient_frames(led_count, rgb, width)

    def build_tags(
        self,
        frames: List[List[List[int]]],
        start_time: float,
        end_time: float,
        step: float,
    ) -> List[Dict[str, Any]]:
        return build_timed_pattern_tags(frames, start_time, end_time, step)

    def build_events(
        self,
        frames: List[List[List[int]]],
        start_time: float,
        step: float,
    ) -> List[PatternEvent]:
        """Expand frames into a flat list of `PatternEvent`s.

        Order: time-major, led-index-minor. Times rounded to 3
        decimal places, matching build_timed_pattern_tags.
        """
        if not frames or step <= 0:
            return []
        events: List[PatternEvent] = []
        for frame_index, frame in enumerate(frames):
            t = round(start_time + frame_index * step, 3)
            for led_index, color in enumerate(frame):
                events.append(
                    PatternEvent(
                        led_index=led_index,
                        color=list(color),
                        time_seconds=t,
                    )
                )
        return events
