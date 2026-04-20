from __future__ import annotations

from typing import List


def validate_wire_assignment(
    cells: List[int],
    canvas_size: int,
    led_count: int,
) -> List[str]:
    """Return a list of validation errors (empty if valid).

    Checks length matches led_count, all cells in [0, canvas_size),
    no duplicates, and canvas_size >= 1.
    """
    errors: List[str] = []
    if canvas_size < 1:
        errors.append(f"canvas_size must be >= 1, got {canvas_size}")
        return errors
    if led_count < 0:
        errors.append(f"led_count must be >= 0, got {led_count}")
    if len(cells) != led_count:
        errors.append(f"wire length {len(cells)} does not match led_count {led_count}")
    out_of_range = [c for c in cells if not (0 <= c < canvas_size)]
    if out_of_range:
        errors.append(f"cells out of canvas [0,{canvas_size}): {sorted(out_of_range)}")
    if len(set(cells)) != len(cells):
        dupes = [c for c in set(cells) if cells.count(c) > 1]
        errors.append(f"duplicate cells: {sorted(dupes)}")
    return errors


def build_linear_wire(led_count: int) -> List[int]:
    """Default wire: linear row-major order [0, 1, ..., N-1]."""
    return list(range(max(0, led_count)))


def add_to_wire(existing: List[int], cell: int) -> List[int]:
    """Append cell to wire. Caller ensures cell not in existing."""
    return [*existing, int(cell)]


def remove_from_wire(
    existing: List[int],
    cell: int,
) -> List[int]:
    """Remove cell from wire; remaining cells keep relative order
    so their wire indices remap naturally via list position."""
    return [c for c in existing if c != cell]
