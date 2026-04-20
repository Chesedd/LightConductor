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

BEGIN_STRUCT = struct.Struct("<4sBBII")  # magic, cmd, slave_id, total_size, crc32
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
            f"UDP send to {host}:{port} failed after {attempts} attempt(s): {original}"
        )


class UploadCancelledError(Exception):
    """Raised when a progress callback returns False.

    Carries progress counters so callers can report how much was sent
    before cancel.
    """

    def __init__(self, packets_sent: int, total_packets: int):
        self.packets_sent = packets_sent
        self.total_packets = total_packets
        super().__init__(
            f"upload cancelled after {packets_sent} of {total_packets} packet(s)"
        )


def count_upload_packets(
    compiled_by_host: Optional[Dict[str, List[CompiledSlaveShow]]],
    chunk_size: int,
) -> int:
    """Total sendto() calls an upload() invocation will make for the
    given compiled input. Mirrors the packet-count arithmetic in
    upload_plan.build_upload_plan but intentionally re-derived here to
    keep the transport standalone (no reverse import from application
    layer).
    """
    size = max(1, int(chunk_size))
    total = 0
    for _host, shows in (compiled_by_host or {}).items():
        for show in shows:
            blob_size = len(show.blob or b"")
            chunk_count = -(-blob_size // size)
            total += 2 + chunk_count  # BEGIN + chunks + END
    return total


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
        d = base * (2**i)
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
                    "UDP send to %s:%s failed on attempt %d/%d: %s; retrying in %.3fs",
                    addr[0],
                    addr[1],
                    attempts,
                    1 + len(self._retry_delays),
                    exc,
                    delay,
                )
                if delay > 0.0:
                    time.sleep(delay)
        logger.error(
            "UDP send to %s:%s exhausted retries after %d attempt(s)",
            addr[0],
            addr[1],
            attempts,
        )
        raise UploadFailedError(
            host=addr[0],
            port=addr[1],
            attempts=attempts,
            original=last_error,
        )

    def upload(
        self,
        compiled_by_host: Dict[str, List[CompiledSlaveShow]],
        *,
        progress_callback: Optional[Callable[[int, int], bool]] = None,
    ) -> None:
        total = count_upload_packets(
            compiled_by_host,
            self.chunk_size,
        )
        sent = 0

        def _after_send():
            nonlocal sent
            sent += 1
            if progress_callback is None:
                return
            if progress_callback(sent, total) is False:
                raise UploadCancelledError(sent, total)

        sock = self._socket_factory()
        try:
            for host, shows in compiled_by_host.items():
                addr = (host, self.port)
                for show in shows:
                    self._send_with_retry(
                        sock,
                        BEGIN_STRUCT.pack(
                            APP_MAGIC,
                            CMD_UPLOAD_BEGIN,
                            show.slave_id,
                            len(show.blob),
                            show.crc32,
                        ),
                        addr,
                    )
                    _after_send()
                    time.sleep(self.inter_packet_delay)

                    offset = 0
                    while offset < len(show.blob):
                        chunk = show.blob[offset : offset + self.chunk_size]
                        packet = (
                            CHUNK_HEAD_STRUCT.pack(
                                APP_MAGIC,
                                CMD_UPLOAD_CHUNK,
                                show.slave_id,
                                offset,
                                len(chunk),
                            )
                            + chunk
                        )
                        self._send_with_retry(sock, packet, addr)
                        _after_send()
                        offset += len(chunk)
                        time.sleep(self.inter_packet_delay)

                    self._send_with_retry(
                        sock,
                        END_STRUCT.pack(APP_MAGIC, CMD_UPLOAD_END, show.slave_id),
                        addr,
                    )
                    _after_send()
                    time.sleep(self.inter_packet_delay)
        finally:
            sock.close()

    def start_show(
        self,
        hosts: Iterable[str],
        *,
        progress_callback: Optional[Callable[[int, int], bool]] = None,
    ) -> None:
        unique_hosts = sorted({host for host in hosts if host})
        total = len(unique_hosts)
        sent = 0
        sock = self._socket_factory()
        try:
            payload = START_STRUCT.pack(APP_MAGIC, CMD_START_SHOW)
            for host in unique_hosts:
                self._send_with_retry(sock, payload, (host, self.port))
                sent += 1
                if progress_callback is not None:
                    if progress_callback(sent, total) is False:
                        raise UploadCancelledError(sent, total)
                time.sleep(self.inter_packet_delay)
        finally:
            sock.close()
