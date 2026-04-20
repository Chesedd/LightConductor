import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.pattern_service import (
    PatternEvent,
    PatternService,
)
from lightconductor.application.patterns import (
    apply_fill_range,
    build_timed_pattern_tags,
    floating_gradient_frames,
    moving_window_frames,
    sequential_fill_frames,
    solid_fill,
)


class PatternServiceDelegationTests(unittest.TestCase):
    def setUp(self):
        self.service = PatternService()

    def test_solid_fill_delegates(self):
        self.assertEqual(
            solid_fill(3, [1, 2, 3]),
            self.service.solid_fill(3, [1, 2, 3]),
        )
        self.assertEqual(
            [[1, 2, 3], [1, 2, 3], [1, 2, 3]],
            self.service.solid_fill(3, [1, 2, 3]),
        )

    def test_apply_fill_range_delegates(self):
        colors = [[0, 0, 0] for _ in range(5)]
        self.assertEqual(
            apply_fill_range(colors, 1, 3, [9, 8, 7]),
            self.service.apply_fill_range(colors, 1, 3, [9, 8, 7]),
        )

    def test_sequential_fill_delegates(self):
        self.assertEqual(
            sequential_fill_frames(3, [5, 6, 7]),
            self.service.sequential_fill(3, [5, 6, 7]),
        )

    def test_moving_window_delegates(self):
        self.assertEqual(
            moving_window_frames(4, 2, [1, 2, 3]),
            self.service.moving_window(4, 2, [1, 2, 3]),
        )

    def test_floating_gradient_delegates_with_default_width(self):
        self.assertEqual(
            floating_gradient_frames(5, [100, 0, 0], 4),
            self.service.floating_gradient(5, [100, 0, 0]),
        )

    def test_floating_gradient_delegates_with_custom_width(self):
        self.assertEqual(
            floating_gradient_frames(5, [100, 0, 0], 2),
            self.service.floating_gradient(5, [100, 0, 0], 2),
        )

    def test_build_tags_delegates(self):
        frames = [[[1, 1, 1]], [[2, 2, 2]]]
        self.assertEqual(
            build_timed_pattern_tags(frames, 0.0, 0.5, 0.25),
            self.service.build_tags(frames, 0.0, 0.5, 0.25),
        )


class PatternServiceBuildEventsTests(unittest.TestCase):
    def setUp(self):
        self.service = PatternService()

    def test_build_events_empty_frames_returns_empty(self):
        self.assertEqual([], self.service.build_events([], 0.0, 0.25))

    def test_build_events_zero_step_returns_empty(self):
        frames = [[[1, 2, 3]]]
        self.assertEqual([], self.service.build_events(frames, 0.0, 0.0))

    def test_build_events_negative_step_returns_empty(self):
        frames = [[[1, 2, 3]]]
        self.assertEqual([], self.service.build_events(frames, 0.0, -0.1))

    def test_build_events_single_frame_single_led(self):
        events = self.service.build_events([[[7, 7, 7]]], 0.0, 0.5)
        self.assertEqual(1, len(events))
        self.assertEqual(0, events[0].led_index)
        self.assertEqual([7, 7, 7], events[0].color)
        self.assertEqual(0.0, events[0].time_seconds)

    def test_build_events_multi_frame_multi_led_time_major_order(self):
        frames = [
            [[1, 0, 0], [2, 0, 0], [3, 0, 0]],
            [[4, 0, 0], [5, 0, 0], [6, 0, 0]],
        ]
        events = self.service.build_events(frames, 0.1, 0.2)
        self.assertEqual(6, len(events))
        self.assertEqual(
            [
                (0, [1, 0, 0], 0.1),
                (1, [2, 0, 0], 0.1),
                (2, [3, 0, 0], 0.1),
                (0, [4, 0, 0], 0.3),
                (1, [5, 0, 0], 0.3),
                (2, [6, 0, 0], 0.3),
            ],
            [(e.led_index, e.color, e.time_seconds) for e in events],
        )

    def test_build_events_rounds_time_to_three_decimals(self):
        frames = [[[1, 1, 1]]] * 3
        events = self.service.build_events(frames, 0.0, 1 / 3)
        self.assertEqual(0.667, events[2].time_seconds)


class PatternEventTests(unittest.TestCase):
    def test_pattern_event_is_frozen(self):
        event = PatternEvent(led_index=0, color=[1, 2, 3], time_seconds=0.0)
        with self.assertRaises(Exception):  # noqa: B017 - frozen dataclass raises FrozenInstanceError; test only cares that assignment fails
            event.led_index = 99


class PatternServiceStatelessTests(unittest.TestCase):
    def test_pattern_service_is_stateless(self):
        a = PatternService()
        b = PatternService()
        self.assertEqual(
            a.solid_fill(3, [1, 2, 3]),
            b.solid_fill(3, [1, 2, 3]),
        )


if __name__ == "__main__":
    unittest.main()
