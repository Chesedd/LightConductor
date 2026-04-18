from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol, Tuple

from lightconductor.application.compiled_show import CompileShowsForMastersUseCase
from lightconductor.infrastructure.legacy_mappers import LegacyMastersMapper
from lightconductor.infrastructure.master_udp_upload_transport import MasterUdpUploadTransport


class AudioLoaderPort(Protocol):
    def load(self, file_path: str) -> Tuple[Any, int, str]:
        ...


@dataclass(slots=True)
class ProjectScreenController:
    mapper: LegacyMastersMapper
    compile_use_case: CompileShowsForMastersUseCase
    transport: MasterUdpUploadTransport
    audio_loader: AudioLoaderPort

    def upload_show(self, legacy_masters: Dict[str, Any]) -> None:
        masters = self.mapper.map_masters(legacy_masters)
        compiled_by_host = self.compile_use_case.execute(masters)
        self.transport.upload(compiled_by_host)

    def send_start_signal(self, legacy_masters: Dict[str, Any]) -> None:
        masters = self.mapper.map_masters(legacy_masters)
        self.transport.start_show(master.ip for master in masters.values())

    def load_track(self, file_path: str) -> Tuple[Any, int, str]:
        return self.audio_loader.load(file_path)