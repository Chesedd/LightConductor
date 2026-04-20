"""Test-support: a minimal UDP receiver bound to 127.0.0.1 plus helpers
to parse the LightConductor wire protocol. Used by test_udp_integration
and reusable by future Phase 6 tests (retry, backoff). NOT a pytest test
file -- underscore prefix keeps it out of test discovery.
"""

from __future__ import annotations

import socket
import sys
import threading
import zlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.infrastructure.master_udp_upload_transport import (  # noqa: E402
    APP_MAGIC,
    BEGIN_STRUCT,
    CHUNK_HEAD_STRUCT,
    CMD_START_SHOW,
    CMD_UPLOAD_BEGIN,
    CMD_UPLOAD_CHUNK,
    CMD_UPLOAD_END,
    END_STRUCT,
    START_STRUCT,
)


@dataclass
class MockUdpReceiver:
    """UDP receiver on 127.0.0.1. Collects all datagrams into .packets
    (list of bytes). Thread-safe append.
    """

    port: int = 0
    packets: List[bytes] = field(default_factory=list)
    _sock: socket.socket | None = None
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> None:
        """Create socket, bind, spawn receive thread. Sets self.port to
        the OS-chosen port.
        """
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.settimeout(0.5)
        self.port = self._sock.getsockname()[1]
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                data, _addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                return
            with self._lock:
                self.packets.append(data)

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def snapshot(self) -> List[bytes]:
        """Return a copy of packets captured so far."""
        with self._lock:
            return list(self.packets)


@contextmanager
def mock_udp_receiver():
    """Context-manager shorthand:

    with mock_udp_receiver() as recv:
        # recv.port is the bound port
        # ... run transport ...
    # thread joined on exit
    """
    recv = MockUdpReceiver()
    recv.start()
    try:
        yield recv
    finally:
        recv.stop()


# --- Protocol parsing helpers -------------------------------------------


@dataclass(frozen=True)
class ParsedBegin:
    slave_id: int
    total_size: int
    crc32: int


@dataclass(frozen=True)
class ParsedChunk:
    slave_id: int
    offset: int
    chunk_len: int
    payload: bytes


@dataclass(frozen=True)
class ParsedEnd:
    slave_id: int


def parse_packet(data: bytes):
    """Return one of ParsedBegin / ParsedChunk / ParsedEnd / the string
    "start" / None (unknown). Pure.
    """
    if len(data) < 5:
        return None
    magic = data[:4]
    cmd = data[4]
    if magic != APP_MAGIC:
        return None
    if cmd == CMD_UPLOAD_BEGIN:
        if len(data) != BEGIN_STRUCT.size:
            return None
        _m, _c, slave_id, total_size, crc32 = BEGIN_STRUCT.unpack(data)
        return ParsedBegin(slave_id, total_size, crc32)
    if cmd == CMD_UPLOAD_CHUNK:
        if len(data) < CHUNK_HEAD_STRUCT.size:
            return None
        _m, _c, slave_id, offset, chunk_len = CHUNK_HEAD_STRUCT.unpack(
            data[: CHUNK_HEAD_STRUCT.size]
        )
        payload = data[CHUNK_HEAD_STRUCT.size : CHUNK_HEAD_STRUCT.size + chunk_len]
        if len(payload) != chunk_len:
            return None
        return ParsedChunk(slave_id, offset, chunk_len, payload)
    if cmd == CMD_UPLOAD_END:
        if len(data) != END_STRUCT.size:
            return None
        _m, _c, slave_id = END_STRUCT.unpack(data)
        return ParsedEnd(slave_id)
    if cmd == CMD_START_SHOW:
        if len(data) != START_STRUCT.size:
            return None
        return "start"
    return None


def reassemble_blobs(packets: List[bytes]) -> Dict[int, bytes]:
    """For each slave_id that has BEGIN + N CHUNK + END, reassemble the
    blob by sorting CHUNKs on offset and concatenating payloads. Returns
    {slave_id: blob}. Slaves without a matching END are omitted.
    """
    begins: Dict[int, ParsedBegin] = {}
    chunks_by_slave: Dict[int, List[ParsedChunk]] = {}
    ended: set[int] = set()
    for raw in packets:
        parsed = parse_packet(raw)
        if isinstance(parsed, ParsedBegin):
            begins[parsed.slave_id] = parsed
        elif isinstance(parsed, ParsedChunk):
            chunks_by_slave.setdefault(parsed.slave_id, []).append(parsed)
        elif isinstance(parsed, ParsedEnd):
            ended.add(parsed.slave_id)
    result: Dict[int, bytes] = {}
    for slave_id in ended:
        if slave_id not in begins:
            continue
        chunks = sorted(
            chunks_by_slave.get(slave_id, []),
            key=lambda c: c.offset,
        )
        blob = b"".join(c.payload for c in chunks)
        result[slave_id] = blob
    return result


def start_packet_count(packets: List[bytes]) -> int:
    """Count START_SHOW packets."""
    return sum(1 for p in packets if parse_packet(p) == "start")


def crc32_of(blob: bytes) -> int:
    return zlib.crc32(blob) & 0xFFFFFFFF


# --- Failure-injection helpers for retry tests --------------------------


class FailingSocket:
    """Test double for socket.socket(SOCK_DGRAM) used by _send_with_retry
    tests. Records all sendto attempts.

    Configure via:
        failures: a list/iterable of OSError-or-None per sendto call.
            None = success. OSError = raise. When the iterable is
            exhausted, subsequent sendto calls succeed silently.
        record: list of (data, addr) tuples appended on every sendto
            attempt (including failed ones).

    Methods used by transport:
        sendto(data, addr) -> int (bytes sent on success)
        close() -> None
    """

    def __init__(self, failures=None):
        self._failures = list(failures or [])
        self._failure_idx = 0
        self.record: list = []
        self.closed = False

    def sendto(self, data, addr):
        self.record.append((data, addr))
        if self._failure_idx < len(self._failures):
            slot = self._failures[self._failure_idx]
            self._failure_idx += 1
            if isinstance(slot, OSError):
                raise slot
            if isinstance(slot, type) and issubclass(slot, OSError):
                raise slot()
        return len(data)

    def close(self):
        self.closed = True

    @property
    def attempt_count(self):
        return len(self.record)


def make_failing_socket_factory(*failure_lists):
    """Return a factory that yields a fresh FailingSocket per call,
    walking through ``failure_lists`` in order. Use when a test wants to
    track multiple sockets (each upload() call constructs a fresh
    socket).
    """
    sockets: list = []
    iterator = iter(failure_lists)

    def _factory():
        try:
            failures = next(iterator)
        except StopIteration:
            failures = []
        s = FailingSocket(failures=failures)
        sockets.append(s)
        return s

    _factory.sockets = sockets
    return _factory
