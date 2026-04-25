from __future__ import annotations

import logging
import select
import socket
import struct
import time
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from lightconductor.application.compiled_show import CompiledSlaveShow

logger = logging.getLogger(__name__)

APP_MAGIC = b"LCM1"

CMD_UPLOAD_BEGIN = 0x10
CMD_UPLOAD_CHUNK = 0x11
CMD_UPLOAD_END = 0x12
CMD_START_SHOW = 0x20
CMD_ACK = 0x30

BEGIN_STRUCT = struct.Struct("<4sBBII")  # magic, cmd, slave_id, total_size, crc32
CHUNK_HEAD_STRUCT = struct.Struct("<4sBBIH")  # magic, cmd, slave_id, offset, chunk_len
END_STRUCT = struct.Struct("<4sBB")
START_STRUCT = struct.Struct("<4sB")
# magic, cmd(=CMD_ACK), acked_cmd, slave_id, offset
# offset is meaningful only for CHUNK; BEGIN/END use offset=0 as a sentinel.
ACK_STRUCT = struct.Struct("<4sBBBI")

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY = 0.05
DEFAULT_RETRY_MAX_DELAY = 1.0

DEFAULT_ACK_TIMEOUT_S = 0.2
DEFAULT_ACK_MAX_RETRIES = 3
DEFAULT_ACK_BACKOFF: Tuple[float, ...] = (0.1, 0.2, 0.4)


class UploadFailedError(Exception):
    """Raised when a UDP send exhausts its retry budget.

    Attributes:
        host: target host address.
        port: target port.
        attempts: total number of sendto attempts made (initial + retries).
        original: the last OSError raised by sendto.
    """

    def __init__(
        self,
        host: str,
        port: int,
        attempts: int,
        original: Optional[OSError],
    ) -> None:
        self.host = host
        self.port = port
        self.attempts = attempts
        self.original = original
        super().__init__(
            f"UDP send to {host}:{port} failed after {attempts} attempt(s): {original}"
        )


class AckTimeoutError(UploadFailedError):
    """Raised when a :meth:`MasterUdpUploadTransport._send_with_ack` call
    exhausts its retry budget without receiving a matching CMD_ACK.

    Attributes:
        acked_cmd: the command byte the master was expected to echo
            (CMD_UPLOAD_BEGIN, CMD_UPLOAD_CHUNK, CMD_UPLOAD_END, ...).
        slave_id: the target slave id encoded in the sent packet.
        offset: the CHUNK byte offset for CHUNK packets, or 0 for
            BEGIN/END (sentinel).
        attempts: total number of sendto attempts made (initial + retries).
    """

    def __init__(
        self,
        *,
        acked_cmd: int,
        slave_id: int,
        offset: int,
        attempts: int,
        addr: Tuple[str, int],
    ) -> None:
        self.acked_cmd = acked_cmd
        self.slave_id = slave_id
        self.offset = offset
        # NB: we intentionally bypass UploadFailedError.__init__ here; the
        # base class's constructor expects an OSError which does not apply
        # to ACK timeouts. We still satisfy isinstance(UploadFailedError)
        # for callers that catch the broader type.
        self.host = addr[0]
        self.port = addr[1]
        self.attempts = attempts
        self.original = None
        Exception.__init__(
            self,
            f"No ACK received for cmd={acked_cmd:#x} slave_id={slave_id} "
            f"offset={offset} after {attempts} attempt(s) to "
            f"{addr[0]}:{addr[1]}",
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
        ack_timeout_s: float = DEFAULT_ACK_TIMEOUT_S,
        ack_max_retries: int = DEFAULT_ACK_MAX_RETRIES,
        ack_backoff_delays: Tuple[float, ...] = DEFAULT_ACK_BACKOFF,
        use_ack: bool = True,
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
        self.ack_timeout_s = max(0.0, float(ack_timeout_s))
        self.ack_max_retries = max(0, int(ack_max_retries))
        self.ack_backoff_delays = tuple(max(0.0, float(d)) for d in ack_backoff_delays)
        self.use_ack = bool(use_ack)

    def _send_with_retry(
        self,
        sock: socket.socket,
        data: bytes,
        addr: Tuple[str, int],
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

    def _send_with_ack(
        self,
        sock: socket.socket,
        data: bytes,
        addr: Tuple[str, int],
        *,
        expected_cmd: int,
        slave_id: int,
        offset: int = 0,
    ) -> None:
        """Send ``data`` to ``addr`` and block until a matching CMD_ACK
        arrives on ``sock`` within :attr:`ack_timeout_s`. On timeout,
        retry up to :attr:`ack_max_retries` times, sleeping the
        corresponding entry of :attr:`ack_backoff_delays` between
        retries. Raise :class:`AckTimeoutError` after exhausting all
        attempts.

        A received packet is considered a match only if it parses as
        ``ACK_STRUCT``, has magic == ``APP_MAGIC``, ``cmd`` byte equal
        to ``CMD_ACK`` and ``(acked_cmd, slave_id, offset)`` equal to
        the expected tuple. Non-matching packets (wrong magic, wrong
        cmd, stale offsets from prior retries, ACKs for other slaves)
        are silently dropped and the wait continues within the current
        attempt's remaining time budget.
        """
        max_attempts = 1 + self.ack_max_retries
        attempts = 0
        while True:
            attempts += 1
            sock.sendto(data, addr)
            deadline = time.monotonic() + self.ack_timeout_s
            got_ack = False
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    break
                ready, _, _ = select.select([sock], [], [], remaining)
                if not ready:
                    break
                try:
                    packet, _src = sock.recvfrom(ACK_STRUCT.size)
                except (BlockingIOError, InterruptedError):
                    continue
                if len(packet) != ACK_STRUCT.size:
                    continue
                try:
                    magic, cmd, ack_cmd, ack_slave, ack_offset = ACK_STRUCT.unpack(
                        packet
                    )
                except struct.error:
                    continue
                if magic != APP_MAGIC or cmd != CMD_ACK:
                    continue
                if (
                    ack_cmd != expected_cmd
                    or ack_slave != slave_id
                    or ack_offset != offset
                ):
                    continue
                got_ack = True
                break
            if got_ack:
                return
            if attempts >= max_attempts:
                logger.error(
                    "No ACK from %s:%s for cmd=%#x slave_id=%d offset=%d "
                    "after %d attempt(s)",
                    addr[0],
                    addr[1],
                    expected_cmd,
                    slave_id,
                    offset,
                    attempts,
                )
                raise AckTimeoutError(
                    acked_cmd=expected_cmd,
                    slave_id=slave_id,
                    offset=offset,
                    attempts=attempts,
                    addr=addr,
                )
            if self.ack_backoff_delays:
                idx = min(attempts - 1, len(self.ack_backoff_delays) - 1)
                delay = self.ack_backoff_delays[idx]
                logger.warning(
                    "ACK timeout from %s:%s for cmd=%#x slave_id=%d "
                    "offset=%d on attempt %d/%d; retrying in %.3fs",
                    addr[0],
                    addr[1],
                    expected_cmd,
                    slave_id,
                    offset,
                    attempts,
                    max_attempts,
                    delay,
                )
                if delay > 0.0:
                    time.sleep(delay)

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

        def _after_send() -> None:
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
                    begin_packet = BEGIN_STRUCT.pack(
                        APP_MAGIC,
                        CMD_UPLOAD_BEGIN,
                        show.slave_id,
                        len(show.blob),
                        show.crc32,
                    )
                    if self.use_ack:
                        self._send_with_ack(
                            sock,
                            begin_packet,
                            addr,
                            expected_cmd=CMD_UPLOAD_BEGIN,
                            slave_id=show.slave_id,
                            offset=0,
                        )
                    else:
                        self._send_with_retry(sock, begin_packet, addr)
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
                        if self.use_ack:
                            self._send_with_ack(
                                sock,
                                packet,
                                addr,
                                expected_cmd=CMD_UPLOAD_CHUNK,
                                slave_id=show.slave_id,
                                offset=offset,
                            )
                        else:
                            self._send_with_retry(sock, packet, addr)
                        _after_send()
                        offset += len(chunk)
                        time.sleep(self.inter_packet_delay)

                    end_packet = END_STRUCT.pack(
                        APP_MAGIC, CMD_UPLOAD_END, show.slave_id
                    )
                    if self.use_ack:
                        self._send_with_ack(
                            sock,
                            end_packet,
                            addr,
                            expected_cmd=CMD_UPLOAD_END,
                            slave_id=show.slave_id,
                            offset=0,
                        )
                    else:
                        self._send_with_retry(sock, end_packet, addr)
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
        # CMD_START_SHOW is fire-and-forget by wire-protocol design; the
        # master never emits an ACK for it, so this method deliberately
        # stays on _send_with_retry regardless of self.use_ack.
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
