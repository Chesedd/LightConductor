from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional, Protocol, Tuple

from lightconductor.application.compiled_show import CompileShowsForMastersUseCase
from lightconductor.domain.models import Master
from lightconductor.infrastructure.master_udp_upload_transport import (
    MasterUdpUploadTransport,
)


class AudioLoaderPort(Protocol):
    def load(self, file_path: str) -> Tuple[Any, int, str]: ...


@dataclass(slots=True)
class ProjectScreenController:
    compile_use_case: CompileShowsForMastersUseCase
    transport: MasterUdpUploadTransport
    audio_loader: AudioLoaderPort

    def upload_show(
        self,
        masters: Dict[str, Master],
        *,
        selected_master_ids: Optional[Iterable[str]] = None,
        progress_callback: Optional[Callable[[int, int], bool]] = None,
    ) -> None:
        """Compile and upload the show for the given masters.

        ``selected_master_ids`` controls which masters from ``masters``
        are actually compiled and uploaded:

        * ``None`` (default) — all masters are processed (back-compat).
        * Any iterable — coerced to a set; only masters whose id is in
          BOTH the set AND the ``masters`` dict are processed. Unknown
          ids are silently dropped. An empty resulting subset is valid:
          ``compile_use_case.execute({})`` is invoked, returns an empty
          mapping, and ``transport.upload({})`` is a no-op.
        """
        if selected_master_ids is None:
            filtered_masters = masters
        else:
            selected = set(selected_master_ids)
            filtered_masters = {
                mid: master
                for mid, master in masters.items()
                if mid in selected
            }
        compiled_by_host = self.compile_use_case.execute(filtered_masters)
        self.transport.upload(
            compiled_by_host,
            progress_callback=progress_callback,
        )

    def send_start_signal(
        self,
        masters: Dict[str, Master],
        *,
        progress_callback: Optional[Callable[[int, int], bool]] = None,
    ) -> None:
        self.transport.start_show(
            (master.ip for master in masters.values()),
            progress_callback=progress_callback,
        )

    def load_track(self, file_path: str) -> Tuple[Any, int, str]:
        return self.audio_loader.load(file_path)
