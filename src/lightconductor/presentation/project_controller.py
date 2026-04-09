from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from lightconductor.application import BuildShowPayloadUseCase
from lightconductor.infrastructure import LegacyMastersMapper, UdpShowTransport


@dataclass(slots=True)
class ProjectScreenController:
    mapper: LegacyMastersMapper
    payload_use_case: BuildShowPayloadUseCase
    transport: UdpShowTransport

    def send_show_payload(self, legacy_masters: Dict[str, Any]) -> None:
        masters = self.mapper.map_masters(legacy_masters)
        pins, payload = self.payload_use_case.execute(masters)
        self.transport.send_payload(pins, payload)

    def send_start_signal(self) -> None:
        self.transport.send_start()
