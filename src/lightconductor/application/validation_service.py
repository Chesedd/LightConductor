"""Project validation service.

Runs static checks on a project's master/slave/tag_type structure
to surface problems before the user saves or uploads.

Does not raise: returns a list of `ValidationIssue`. Callers
decide how to react to errors vs warnings.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any, Dict, List

from lightconductor.domain.models import Master, Slave, TagType

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


@dataclass(slots=True, frozen=True)
class ValidationIssue:
    """A single validation finding.

    Attributes:
        severity:  "error" | "warning". Errors block save/upload.
        category:  Machine-readable kind; one of:
                   "overlap", "out_of_bounds",
                   "duplicate_segment_start",
                   "duplicate_slave_pin", "invalid_ip",
                   "gap",
                   "led_cells_mismatch",
                   "led_cells_duplicate",
                   "led_cells_out_of_canvas",
                   "canvas_too_small_for_leds",
                   "canvas_zero",
                   "topology_non_led_cell",
                   "brightness_out_of_range".
        path:      Dotted path pointing to the offending element,
                   e.g. "masters.m1.slaves.s1.tag_types.front".
                   Used for UI highlighting / grouping.
        message:   Human-readable description (English).
    """

    severity: str
    category: str
    path: str
    message: str


class ValidationService:
    """Stateless validation of a `Dict[str, Master]` project tree."""

    def validate(self, masters: Dict[str, Master]) -> List[ValidationIssue]:
        """Run all checks. Returns an empty list if the project
        is valid. Errors and warnings are interleaved in the
        order the checks are run (not sorted)."""
        issues: List[ValidationIssue] = []
        for master_id, master in masters.items():
            master_path = f"masters.{master_id}"
            issues.extend(self._check_ip(master, master_path))
            issues.extend(self._check_duplicate_slave_pins(master, master_path))
            for slave_id, slave in master.slaves.items():
                slave_path = f"{master_path}.slaves.{slave_id}"
                issues.extend(self._check_led_cells(slave, slave_path))
                issues.extend(self._check_topology_cells_have_leds(slave, slave_path))
                issues.extend(self._check_slave_segments(slave, slave_path))
                issues.extend(self._check_slave_brightness_range(slave, slave_path))
        return issues

    # --- individual checks ---

    def _check_ip(self, master: Master, path: str) -> List[ValidationIssue]:
        try:
            ipaddress.IPv4Address(master.ip)
            return []
        except (ValueError, ipaddress.AddressValueError, TypeError):
            return [
                ValidationIssue(
                    severity=SEVERITY_ERROR,
                    category="invalid_ip",
                    path=path,
                    message=f"Master IP is not a valid IPv4 address: {master.ip!r}",
                )
            ]

    def _check_duplicate_slave_pins(
        self,
        master: Master,
        path: str,
    ) -> List[ValidationIssue]:
        seen: Dict[str, List[str]] = {}
        for slave_id, slave in master.slaves.items():
            seen.setdefault(str(slave.pin), []).append(slave_id)
        issues: List[ValidationIssue] = []
        for pin, ids in seen.items():
            if len(ids) > 1:
                issues.append(
                    ValidationIssue(
                        severity=SEVERITY_ERROR,
                        category="duplicate_slave_pin",
                        path=path,
                        message=(
                            f"Duplicate slave pin {pin!r} in master: "
                            f"slaves {sorted(ids)}"
                        ),
                    )
                )
        return issues

    def _check_led_cells(
        self,
        slave: Slave,
        path: str,
    ) -> List[ValidationIssue]:
        """Check invariants on led_cells + canvas + led_count.

        I1: len(led_cells) == led_count.
        I2: all values are unique.
        I3: all values are in [0, grid_rows * grid_columns).
        I4: grid_rows >= 1 AND grid_columns >= 1.
        I5: led_count <= canvas size.
        """
        issues: List[ValidationIssue] = []
        rows = self._safe_int(getattr(slave, "grid_rows", 0))
        cols = self._safe_int(getattr(slave, "grid_columns", 0))
        led_count = self._safe_int(getattr(slave, "led_count", 0))
        led_cells = list(getattr(slave, "led_cells", []) or [])
        canvas = rows * cols

        if rows < 1 or cols < 1:
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_ERROR,
                    category="canvas_zero",
                    path=path,
                    message=(f"Canvas dimensions must be >= 1x1, got {rows}x{cols}"),
                )
            )
            return issues

        if led_count > canvas:
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_ERROR,
                    category="canvas_too_small_for_leds",
                    path=path,
                    message=(
                        f"led_count={led_count} exceeds canvas "
                        f"size {rows}*{cols}={canvas}"
                    ),
                )
            )

        if len(led_cells) != led_count:
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_ERROR,
                    category="led_cells_mismatch",
                    path=path,
                    message=(
                        f"led_cells length {len(led_cells)} "
                        f"does not match led_count {led_count}"
                    ),
                )
            )

        if len(set(led_cells)) != len(led_cells):
            dupes = [c for c in set(led_cells) if led_cells.count(c) > 1]
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_ERROR,
                    category="led_cells_duplicate",
                    path=path,
                    message=(f"led_cells contains duplicate values: {sorted(dupes)}"),
                )
            )

        out_of_range = [c for c in led_cells if c < 0 or c >= canvas]
        if out_of_range:
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_ERROR,
                    category="led_cells_out_of_canvas",
                    path=path,
                    message=(
                        f"led_cells values out of canvas "
                        f"[0,{canvas}): {sorted(out_of_range)}"
                    ),
                )
            )

        return issues

    def _check_topology_cells_have_leds(
        self,
        slave: Slave,
        path: str,
    ) -> List[ValidationIssue]:
        """I6: every TagType.topology cell must be in led_cells."""
        issues: List[ValidationIssue] = []
        led_cells_set = set(getattr(slave, "led_cells", []) or [])
        for type_name, tag_type in (slave.tag_types or {}).items():
            topology = list(getattr(tag_type, "topology", []) or [])
            non_led = [c for c in topology if c not in led_cells_set]
            if non_led:
                issues.append(
                    ValidationIssue(
                        severity=SEVERITY_ERROR,
                        category="topology_non_led_cell",
                        path=f"{path}.tag_types.{type_name}",
                        message=(
                            f"TagType {type_name!r} references cells "
                            f"without LEDs: {sorted(non_led)}"
                        ),
                    )
                )
        return issues

    def _check_slave_segments(
        self,
        slave: Slave,
        path: str,
    ) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        segments: List[Dict[str, Any]] = []
        canvas = self._safe_int(getattr(slave, "grid_rows", 0)) * self._safe_int(
            getattr(slave, "grid_columns", 0)
        )
        for tag_type_name, tag_type in slave.tag_types.items():
            start = self._safe_int(tag_type.pin)
            size = self._segment_size(tag_type)
            segments.append(
                {
                    "start": start,
                    "size": size,
                    "name": tag_type_name,
                }
            )
            if canvas > 0 and start + size > canvas:
                issues.append(
                    ValidationIssue(
                        severity=SEVERITY_ERROR,
                        category="out_of_bounds",
                        path=f"{path}.tag_types.{tag_type_name}",
                        message=(
                            f"Segment [{start}..{start + size - 1}] "
                            f"exceeds slave canvas size {canvas}"
                        ),
                    )
                )
        by_start: Dict[int, List[str]] = {}
        for seg in segments:
            by_start.setdefault(seg["start"], []).append(seg["name"])
        for start, names in by_start.items():
            if len(names) > 1:
                issues.append(
                    ValidationIssue(
                        severity=SEVERITY_ERROR,
                        category="duplicate_segment_start",
                        path=path,
                        message=(
                            f"Multiple tag_types at segment_start={start}: "
                            f"{sorted(names)}"
                        ),
                    )
                )
        sorted_segs = sorted(segments, key=lambda s: (s["start"], s["size"]))
        for i in range(len(sorted_segs) - 1):
            a, b = sorted_segs[i], sorted_segs[i + 1]
            if a["start"] == b["start"]:
                continue
            a_end = a["start"] + a["size"]
            if a_end > b["start"]:
                issues.append(
                    ValidationIssue(
                        severity=SEVERITY_ERROR,
                        category="overlap",
                        path=path,
                        message=(
                            f"Segments overlap: {a['name']!r} "
                            f"[{a['start']}..{a_end - 1}] and {b['name']!r} "
                            f"[{b['start']}..{b['start'] + b['size'] - 1}]"
                        ),
                    )
                )
        if len(sorted_segs) >= 2:
            for i in range(len(sorted_segs) - 1):
                a, b = sorted_segs[i], sorted_segs[i + 1]
                a_end = a["start"] + a["size"]
                if a_end < b["start"]:
                    issues.append(
                        ValidationIssue(
                            severity=SEVERITY_WARNING,
                            category="gap",
                            path=path,
                            message=(
                                f"Gap between segments {a['name']!r} and "
                                f"{b['name']!r}: LEDs {a_end}..{b['start'] - 1} "
                                f"not covered"
                            ),
                        )
                    )
        return issues

    def _check_slave_brightness_range(
        self,
        slave: Slave,
        path: str,
    ) -> List[ValidationIssue]:
        """Soft warning if brightness lies outside [0.0, 1.0].

        Compile clamps to the valid range, so out-of-range values
        never produce garbage bytes. Save and compile are not
        blocked by this category.
        """
        try:
            brightness = float(getattr(slave, "brightness", 1.0))
        except (TypeError, ValueError):
            return []
        if 0.0 <= brightness <= 1.0:
            return []
        return [
            ValidationIssue(
                severity=SEVERITY_WARNING,
                category="brightness_out_of_range",
                path=path,
                message=(
                    f"Brightness {brightness} for slave {slave.name!r} "
                    f"is outside [0.0, 1.0]; will be clamped on compile"
                ),
            )
        ]

    # --- helpers ---

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _segment_size(tag_type: TagType) -> int:
        """Mirrors CompileShowsForMastersUseCase._segment_size:
        topology length if non-empty, else max(1, rows*columns).
        """
        topology = list(tag_type.topology or [])
        if topology:
            return len(topology)
        return max(1, int(tag_type.rows) * int(tag_type.columns))
