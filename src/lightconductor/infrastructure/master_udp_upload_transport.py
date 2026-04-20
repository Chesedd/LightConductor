from __future__ import annotations

import logging
import socket
import struct
import time
from typing import Callable, Dict, Iterable, List, Optional

from lightconductor.application.compiled_show import CompiledSlaveShow

logger = logging.getLogger(__name__)

APP_MAGIC = b"LCM1"

CMD_UPLOAD_BEGIN = 0x10
CMD_UPLOAD_CHUNK = 0x11
CMD_UPLOAD_END = 0x12
CMD_START_SHOW = 0x20

BEGIN_STRUCT = struct.Struct("<4sBBII")   # magic, cmd, slave_id, total_size, crc32
CHUNK_HEAD_STRUCT = struct.Struct("<4sBBIH")  # magic, cmd, slave_id, offset, chunk_len
END_STRUCT = struct.Struct("<4sBB")
START_STRUCT = struct.Struct("<4sB")

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY = 0.05
DEFAULT_RETRY_MAX_DELAY = 1.0


class UploadFailedError(Exception):
    """Raised when a UDP send exhausts its retry budget.

    Attributes:
        host: target host address.
        port: target port.
        attempts: total number of sendto attempts made (initial + retries).
        original: the last OSError raised by sendto.
    """

    def __init__(self, host, port, attempts, original):
        self.host = host
        self.port = port
        self.attempts = attempts
        self.original = original
        super().__init__(
            f"UDP send to {host}:{port} failed after "
            f"{attempts} attempt(s): {original}"
        )


def compute_backoff_delays(
    max_retries: int,
    base_delay: float,
    max_delay: float,
) -> List[float]:
    """Return the sequence of sleep durations to apply BETWEEN attempts.

    Length = max_retries (we don't sleep before the first attempt). Each
    entry = min(base_delay * 2**attempt_index, max_delay). Negative inputs
    are clamped to 0.0. max_retries < 0 treated as 0.
    """
    n = max(0, int(max_retries))
    base = max(0.0, float(base_delay or 0.0))
    cap = max(0.0, float(max_delay or 0.0))
    if n == 0 or base == 0.0:
        return [0.0] * n
    delays: List[float] = []
    for i in range(n):
        d = base * (2 ** i)
        if cap > 0.0 and d > cap:
            d = cap
        delays.append(d)
    return delays


class MasterUdpUploadTransport:
    def __init__(
        self,
        port: int = 43690,
        chunk_size: int = 768,
        inter_packet_delay: float = 0.002,
        *,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
        retry_max_delay: float = DEFAULT_RETRY_MAX_DELAY,
        socket_factory: Optional[Callable[[], socket.socket]] = None,
    ):
        self.port = port
        self.chunk_size = chunk_size
        self.inter_packet_delay = inter_packet_delay
        self.max_retries = max(0, int(max_retries))
        self.retry_base_delay = max(0.0, float(retry_base_delay))
        self.retry_max_delay = max(0.0, float(retry_max_delay))
        self._socket_factory = socket_factory or (
            lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        )
        self._retry_delays = compute_backoff_delays(
            self.max_retries,
            self.retry_base_delay,
            self.retry_max_delay,
        )

    def _send_with_retry(
        self,
        sock: socket.socket,
        data: bytes,
        addr: tuple,
    ) -> None:
        """Send ``data`` to ``addr`` via ``sock``, retrying on OSError per
        ``self._retry_delays``. Raises :class:`UploadFailedError` after
        exhausting retries. Inter-packet delay is applied by the caller
        after a successful return.
        """
        attempts = 0
        last_error: Optional[OSError] = None
        while True:
            attempts += 1
            try:
                sock.sendto(data, addr)
                return
            except OSError as exc:
                last_error = exc
                retry_index = attempts - 1
                if retry_index >= len(self._retry_delays):
                    break
                delay = self._retry_delays[retry_index]
                logger.warning(
                    "UDP send to %s:%s failed on attempt %d/%d: %s; "
                    "retrying in %.3fs",
                    addr[0], addr[1],
                    attempts,
                    1 + len(self._retry_delays),
                    exc,
                    delay,
                )
                if delay > 0.0:
                    time.sleep(delay)
        logger.error(
            "UDP send to %s:%s exhausted retries after %d attempt(s)",
            addr[0], addr[1], attempts,
        )
        raise UploadFailedError(
            host=addr[0],
            port=addr[1],
            attempts=attempts,
            original=last_error,
        )

    def upload(self, compiled_by_host: Dict[str, List[CompiledSlaveShow]]) -> None:
        sock = self._socket_factory()
        try:
            for host, shows in compiled_by_host.items():
                addr = (host, self.port)
                for show in shows:
                    self._send_with_retry(
                        sock,
                        BEGIN_STRUCT.pack(
                            APP_MAGIC, CMD_UPLOAD_BEGIN,
                            show.slave_id, len(show.blob),
                            show.crc32,
                        ),
                        addr,
                    )
                    time.sleep(self.inter_packet_delay)

                    offset = 0
                    while offset < len(show.blob):
                        chunk = show.blob[offset : offset + self.chunk_size]
                        packet = CHUNK_HEAD_STRUCT.pack(
                            APP_MAGIC,
                            CMD_UPLOAD_CHUNK,
                            show.slave_id,
                            offset,
                            len(chunk),
                        ) + chunk
                        self._send_with_retry(sock, packet, addr)
                        offset += len(chunk)
                        time.sleep(self.inter_packet_delay)

                    self._send_with_retry(
                        sock,
                        END_STRUCT.pack(APP_MAGIC, CMD_UPLOAD_END, show.slave_id),
                        addr,
                    )
                    time.sleep(self.inter_packet_delay)
        finally:
            sock.close()

    def start_show(self, hosts: Iterable[str]) -> None:
        unique_hosts = sorted({host for host in hosts if host})
        sock = self._socket_factory()
        try:
            payload = START_STRUCT.pack(APP_MAGIC, CMD_START_SHOW)
            for host in unique_hosts:
                self._send_with_retry(sock, payload, (host, self.port))
                time.sleep(self.inter_packet_delay)
        finally:
            sock.close()
