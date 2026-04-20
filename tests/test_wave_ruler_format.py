import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ProjectScreen.TagLogic.ruler_format import format_tick_strings


def test_spacing_ge_1_formats_mm_ss():
    assert format_tick_strings([0, 5, 65, 125], 1.0, 1.0) == [
        "0:00",
        "0:05",
        "1:05",
        "2:05",
    ]


def test_spacing_0_5_adds_one_decimal():
    out = format_tick_strings([0.5, 1.5, 61.3], 1.0, 0.5)
    assert out == ["0:00.5", "0:01.5", "1:01.3"]


def test_spacing_0_05_adds_two_decimals():
    out = format_tick_strings([0.12, 1.07, 61.99], 1.0, 0.05)
    assert out == ["0:00.12", "0:01.07", "1:01.99"]


def test_negative_value_formatted_with_minus():
    out = format_tick_strings([-1.5, -61.0], 1.0, 0.5)
    assert out == ["-0:01.5", "-1:01.0"]


def test_rounds_up_into_next_second():
    out = format_tick_strings([0.96], 1.0, 0.5)
    assert out == ["0:01.0"]


def test_empty_values_returns_empty_list():
    assert format_tick_strings([], 1.0, 1.0) == []


def test_non_numeric_value_returns_empty_string_slot():
    out = format_tick_strings([0.0, None, 1.0], 1.0, 1.0)
    assert out == ["0:00", "", "0:01"]


def test_minutes_not_capped_at_59():
    out = format_tick_strings([3600, 7200], 1.0, 1.0)
    assert out == ["60:00", "120:00"]


def test_rounding_carries_into_minutes():
    out = format_tick_strings([59.96], 1.0, 0.5)
    assert out == ["1:00.0"]
