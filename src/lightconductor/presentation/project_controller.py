from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol, Tuple

from lightconductor.application import BuildShowPayloadUseCase
from lightconductor.infrastructure import LegacyMastersMapper, UdpShowTransport


class AudioLoaderPort(Protocol):
    def load(self, file_path: str) -> Tuple[Any, int, str]:
        ...


@dataclass(slots=True)
class ProjectScreenController:
    mapper: LegacyMastersMapper
    payload_use_case: BuildShowPayloadUseCase
    transport: UdpShowTransport
    audio_loader: AudioLoaderPort

    def send_show_payload(self, legacy_masters: Dict[str, Any]) -> None:
        masters = self.mapper.map_masters(legacy_masters)
        pins, payload = self.payload_use_case.execute(masters)
        self.transport.send_payload(pins, payload)

    def send_start_signal(self) -> None:
        self.transport.send_start()

    def load_track(self, file_path: str) -> Tuple[Any, int, str]:
        return self.audio_loader.load(file_path)
