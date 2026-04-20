from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from lightconductor.domain.models import Master


@dataclass(slots=True)
class BuildShowPayloadUseCase:
    """Build transport payload independent from UI framework and sockets."""

    def execute(
        self, masters: Dict[str, Master]
    ) -> tuple[Dict[str, Dict[str, int]], Dict[str, Dict[int, Dict[str, dict]]]]:
        payload: Dict[str, Dict[int, Dict[str, dict]]] = {}
        pins: Dict[str, Dict[str, int]] = {}

        for master in masters.values():
            for slave in master.slaves.values():
                payload.setdefault(slave.pin, {})
                pins.setdefault(slave.pin, {})

                for tag_type in slave.tag_types.values():
                    segment_size = len(getattr(tag_type, "topology", [])) or (
                        tag_type.rows * tag_type.columns
                    )
                    try:
                        segment_start = int(tag_type.pin)
                    except (TypeError, ValueError):
                        segment_start = 0
                    pins[slave.pin][tag_type.name] = segment_size

                    for tag in tag_type.tags:
                        timestamp = round(tag.time_seconds * 1000)
                        payload[slave.pin].setdefault(timestamp, {})
                        payload[slave.pin][timestamp][tag_type.name] = {
                            "segment_start": segment_start,
                            "segment_size": segment_size,
                            "action": tag.action,
                            "colors": tag.colors,
                        }

        return pins, payload
