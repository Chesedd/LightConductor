from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from lightconductor.domain.models import Master, Slave, Tag

MAGIC = b"LCS1"
VERSION = 1

OP_OFF = 0x01
OP_SOLID = 0x02
OP_FILL_RANGE = 0x03
OP_FRAME_RLE = 0x04

HEADER_STRUCT = struct.Struct("<4sBBHHHI")
SEGMENT_STRUCT = struct.Struct("<HH")
FILL_RANGE_STRUCT = struct.Struct("<HHB")
RLE_RUN_STRUCT = struct.Struct("<HB")


@dataclass(slots=True)
class SegmentDef:
    start: int
    size: int
    name: str


@dataclass(slots=True)
class CompiledSlaveShow:
    master_ip: str
    slave_id: int
    total_led_count: int
    blob: bytes

    @property
    def crc32(self) -> int:
        return zlib.crc32(self.blob) & 0xFFFFFFFF


class CompileShowsForMastersUseCase:
    """
    Компилирует редакторские tag-события в компактный бинарный show blob.
    Один blob = один slave.
    """

    def execute(self, masters: Dict[str, Master]) -> Dict[str, List[CompiledSlaveShow]]:
        compiled_by_host: Dict[str, List[CompiledSlaveShow]] = {}

        for master in masters.values():
            host = master.ip or "192.168.0.129"
            compiled_by_host.setdefault(host, [])

            for slave in master.slaves.values():
                compiled_by_host[host].append(
                    self._compile_slave_show(master_ip=host, slave=slave)
                )

        return compiled_by_host

    def _compile_slave_show(self, master_ip: str, slave: Slave) -> CompiledSlaveShow:
        slave_id = self._parse_slave_id(slave.pin)
        segment_defs = self._segment_defs(slave)

        if len(segment_defs) > 255:
            raise ValueError(
                f"Too many segments for slave {slave.name}: {len(segment_defs)}"
            )

        total_led_count = int(slave.led_count or 0)
        if total_led_count <= 0:
            total_led_count = (
                max((segment.start + segment.size) for segment in segment_defs)
                if segment_defs
                else 0
            )

        palette: List[Tuple[int, int, int]] = [(0, 0, 0)]
        palette_map: Dict[Tuple[int, int, int], int] = {(0, 0, 0): 0}

        raw_events: List[Tuple[int, int, int, bytes]] = []

        tag_type_items = sorted(
            slave.tag_types.items(), key=lambda item: self._safe_int(item[1].pin)
        )
        for segment_id, (_, tag_type) in enumerate(tag_type_items):
            segment_size = self._segment_size(tag_type)
            for tag in tag_type.tags:
                timestamp_ms = max(0, round(float(tag.time_seconds) * 1000.0))
                normalized_colors = self._normalize_colors(tag.colors, segment_size)
                opcode, payload = self._classify_event(
                    tag, normalized_colors, palette, palette_map
                )
                raw_events.append((timestamp_ms, segment_id, opcode, payload))

        raw_events.sort(key=lambda item: (item[0], item[1], item[2]))

        events_bytes = bytearray()
        previous_timestamp_ms = 0
        for timestamp_ms, segment_id, opcode, payload in raw_events:
            dt = timestamp_ms - previous_timestamp_ms
            previous_timestamp_ms = timestamp_ms
            events_bytes.extend(self._pack_varuint(dt))
            events_bytes.append(opcode)
            events_bytes.append(segment_id)
            events_bytes.extend(payload)

        segments_bytes = bytearray()
        for segment in segment_defs:
            segments_bytes.extend(SEGMENT_STRUCT.pack(segment.start, segment.size))

        if len(palette) > 255:
            raise ValueError(
                f"Palette too large for slave {slave.name}: {len(palette)} colors. "
                "Increase color-id width or reduce unique colors."
            )

        palette_bytes = bytearray()
        for r, g, b in palette:
            palette_bytes.extend((r & 0xFF, g & 0xFF, b & 0xFF))

        header = HEADER_STRUCT.pack(
            MAGIC,
            VERSION,
            slave_id,
            total_led_count,
            len(segment_defs),
            len(palette),
            len(raw_events),
        )

        blob = bytes(header + segments_bytes + palette_bytes + events_bytes)
        return CompiledSlaveShow(
            master_ip=master_ip,
            slave_id=slave_id,
            total_led_count=total_led_count,
            blob=blob,
        )

    def _segment_defs(self, slave: Slave) -> List[SegmentDef]:
        defs: List[SegmentDef] = []
        for tag_type in sorted(
            slave.tag_types.values(), key=lambda item: self._safe_int(item.pin)
        ):
            defs.append(
                SegmentDef(
                    start=self._safe_int(tag_type.pin),
                    size=self._segment_size(tag_type),
                    name=tag_type.name,
                )
            )
        return defs

    @staticmethod
    def _segment_size(tag_type: Any) -> int:
        topology = list(getattr(tag_type, "topology", []) or [])
        if topology:
            return len(topology)
        return max(1, int(tag_type.rows) * int(tag_type.columns))

    @staticmethod
    def _parse_slave_id(pin_value: str) -> int:
        slave_id = int(pin_value)
        if not 0 <= slave_id <= 255:
            raise ValueError(f"slave.pin must be in [0..255], got {pin_value!r}")
        return slave_id

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _pack_varuint(value: int) -> bytes:
        if value < 0:
            raise ValueError("varuint cannot encode negative values")
        out = bytearray()
        while True:
            byte = value & 0x7F
            value >>= 7
            if value:
                out.append(byte | 0x80)
            else:
                out.append(byte)
                break
        return bytes(out)

    @staticmethod
    def _normalize_color(color_like: Any) -> Tuple[int, int, int]:
        if isinstance(color_like, str):
            parts = [part.strip() for part in color_like.split(",")]
            if len(parts) == 3:
                try:
                    return tuple(max(0, min(255, int(part))) for part in parts)  # type: ignore[return-value]
                except ValueError:
                    pass
            return (0, 0, 0)

        if isinstance(color_like, (list, tuple)) and len(color_like) >= 3:
            return (
                max(0, min(255, int(color_like[0]))),
                max(0, min(255, int(color_like[1]))),
                max(0, min(255, int(color_like[2]))),
            )

        return (0, 0, 0)

    def _normalize_colors(
        self, colors: List[List[int]], segment_size: int
    ) -> List[Tuple[int, int, int]]:
        normalized = [self._normalize_color(color) for color in colors[:segment_size]]
        if len(normalized) < segment_size:
            normalized.extend([(0, 0, 0)] * (segment_size - len(normalized)))
        return normalized

    @staticmethod
    def _action_is_on(action: Any) -> bool:
        if isinstance(action, bool):
            return action
        if isinstance(action, str):
            return action.strip().lower() in {"on", "true", "1", "yes"}
        return bool(action)

    @staticmethod
    def _is_black(color: Tuple[int, int, int]) -> bool:
        return color == (0, 0, 0)

    @staticmethod
    def _all_same(colors: List[Tuple[int, int, int]]) -> bool:
        return all(color == colors[0] for color in colors)

    def _intern_color(
        self,
        color: Tuple[int, int, int],
        palette: List[Tuple[int, int, int]],
        palette_map: Dict[Tuple[int, int, int], int],
    ) -> int:
        color_id = palette_map.get(color)
        if color_id is not None:
            return color_id
        color_id = len(palette)
        palette.append(color)
        palette_map[color] = color_id
        return color_id

    def _classify_event(
        self,
        tag: Tag,
        colors: List[Tuple[int, int, int]],
        palette: List[Tuple[int, int, int]],
        palette_map: Dict[Tuple[int, int, int], int],
    ) -> Tuple[int, bytes]:
        action_on = self._action_is_on(tag.action)
        if (
            not action_on
            or not colors
            or all(self._is_black(color) for color in colors)
        ):
            return OP_OFF, b""

        if self._all_same(colors):
            color_id = self._intern_color(colors[0], palette, palette_map)
            return OP_SOLID, bytes([color_id])

        fill_range = self._try_fill_range(colors)
        if fill_range is not None:
            start, length, color = fill_range
            color_id = self._intern_color(color, palette, palette_map)
            return OP_FILL_RANGE, FILL_RANGE_STRUCT.pack(start, length, color_id)

        return OP_FRAME_RLE, self._encode_frame_rle(colors, palette, palette_map)

    def _try_fill_range(
        self, colors: List[Tuple[int, int, int]]
    ) -> Tuple[int, int, Tuple[int, int, int]] | None:
        non_black_indices = [
            idx for idx, color in enumerate(colors) if not self._is_black(color)
        ]
        if not non_black_indices:
            return None

        first = non_black_indices[0]
        last = non_black_indices[-1]
        run_color = colors[first]

        for idx, color in enumerate(colors):
            if first <= idx <= last:
                if color != run_color:
                    return None
            else:
                if not self._is_black(color):
                    return None

        return first, (last - first + 1), run_color

    def _encode_frame_rle(
        self,
        colors: List[Tuple[int, int, int]],
        palette: List[Tuple[int, int, int]],
        palette_map: Dict[Tuple[int, int, int], int],
    ) -> bytes:
        color_ids = [
            self._intern_color(color, palette, palette_map) for color in colors
        ]
        runs: List[Tuple[int, int]] = []

        current_id = color_ids[0]
        run_len = 1
        for color_id in color_ids[1:]:
            if color_id == current_id and run_len < 0xFFFF:
                run_len += 1
                continue
            runs.append((run_len, current_id))
            current_id = color_id
            run_len = 1
        runs.append((run_len, current_id))

        payload = bytearray(struct.pack("<H", len(runs)))
        for run_len, color_id in runs:
            payload.extend(RLE_RUN_STRUCT.pack(run_len, color_id))
        return bytes(payload)
