"""Unit tests for :meth:`MasterUdpUploadTransport._send_with_ack` (Phase 17.1).

The method is foundation-only in 17.1 and is not yet called from
production code; these tests exercise it in isolation. `select.select`
and `time.sleep` are patched on the transport module so the tests run
in milliseconds regardless of configured ACK timeouts or backoffs.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import List, Optional, Tuple
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.infrastructure import master_udp_upload_transport as mut
from lightconductor.infrastructure.master_udp_upload_transport import (
    ACK_STRUCT,
    APP_MAGIC,
    CMD_ACK,
    CMD_UPLOAD_BEGIN,
    CMD_UPLOAD_CHUNK,
    CMD_UPLOAD_END,
    AckTimeoutError,
    MasterUdpUploadTransport,
)

ADDR: Tuple[str, int] = ("10.0.0.1", 43690)


def _ack(
    acked_cmd: int,
    slave_id: int,
    offset: int = 0,
    *,
    magic: bytes = APP_MAGIC,
    cmd: int = CMD_ACK,
) -> bytes:
    return ACK_STRUCT.pack(magic, cmd, acked_cmd, slave_id, offset)


class _AckMockSocket:
    """Test double for a UDP socket with a scripted ACK arrival plan.

    ``per_send_responses[i]`` is the list of packets that become
    available on the socket after the i-th sendto. An entry of ``None``
    is a "no data" slot that causes the current wait to time out. Bytes
    entries are delivered to :meth:`recvfrom` one at a time.

    When ``per_send_responses`` is exhausted, subsequent sends produce
    no ACK (the wait times out).
    """

    def __init__(self, per_send_responses: List[List[Optional[bytes]]]):
        self._plan: List[List[Optional[bytes]]] = [list(r) for r in per_send_responses]
        self.sends: List[Tuple[bytes, Tuple[str, int]]] = []
        self._pending: List[Optional[bytes]] = []
        self.closed = False

    def sendto(self, data: bytes, addr: Tuple[str, int]) -> int:
        self.sends.append((data, addr))
        self._pending = self._plan.pop(0) if self._plan else []
        return len(data)

    def recvfrom(self, bufsize: int) -> Tuple[bytes, Tuple[str, int]]:
        if not self._pending:
            raise BlockingIOError("no data")
        nxt = self._pending.pop(0)
        if nxt is None:
            raise BlockingIOError("no data")
        return (nxt, ADDR)

    def close(self) -> None:
        self.closed = True

    def _has_data(self) -> bool:
        return bool(self._pending) and self._pending[0] is not None


def _fake_select_factory(timeouts_recorded: List[Optional[float]]):
    def _fake_select(rlist, wlist, xlist, timeout=None):  # noqa: ANN001
        timeouts_recorded.append(timeout)
        for s in rlist:
            if hasattr(s, "_has_data") and s._has_data():
                return ([s], [], [])
        return ([], [], [])

    return _fake_select


class _AckRunner:
    """Helper: run _send_with_ack with select.select and time.sleep
    patched on the transport module. Returns (sleeps, select_timeouts).
    """

    def __init__(self, transport: MasterUdpUploadTransport):
        self.transport = transport
        self.sleeps: List[float] = []
        self.select_timeouts: List[Optional[float]] = []

    def run(
        self,
        sock: _AckMockSocket,
        *,
        expected_cmd: int,
        slave_id: int,
        offset: int = 0,
        data: bytes = b"pkt",
    ) -> None:
        fake_select = _fake_select_factory(self.select_timeouts)
        with (
            mock.patch.object(mut.select, "select", side_effect=fake_select),
            mock.patch.object(
                mut.time, "sleep", side_effect=lambda d: self.sleeps.append(d)
            ),
        ):
            self.transport._send_with_ack(
                sock,  # type: ignore[arg-type]
                data,
                ADDR,
                expected_cmd=expected_cmd,
                slave_id=slave_id,
                offset=offset,
            )


def _make_transport(**overrides) -> MasterUdpUploadTransport:  # noqa: ANN003
    kwargs = dict(
        port=43690,
        inter_packet_delay=0.0,
        ack_timeout_s=0.2,
        ack_max_retries=3,
        ack_backoff_delays=(0.1, 0.2, 0.4),
    )
    kwargs.update(overrides)
    return MasterUdpUploadTransport(**kwargs)  # type: ignore[arg-type]


class SendWithAckTests(unittest.TestCase):
    def test_ack_first_try(self) -> None:
        sock = _AckMockSocket([[_ack(CMD_UPLOAD_BEGIN, slave_id=7)]])
        runner = _AckRunner(_make_transport())
        runner.run(sock, expected_cmd=CMD_UPLOAD_BEGIN, slave_id=7)

        self.assertEqual(1, len(sock.sends))
        self.assertEqual([], runner.sleeps)

    def test_ack_after_one_retry(self) -> None:
        sock = _AckMockSocket(
            [
                [None],
                [_ack(CMD_UPLOAD_BEGIN, slave_id=7)],
            ]
        )
        runner = _AckRunner(_make_transport())
        runner.run(sock, expected_cmd=CMD_UPLOAD_BEGIN, slave_id=7)

        self.assertEqual(2, len(sock.sends))
        self.assertEqual([0.1], runner.sleeps)

    def test_ack_after_two_retries(self) -> None:
        sock = _AckMockSocket(
            [
                [None],
                [None],
                [_ack(CMD_UPLOAD_CHUNK, slave_id=3, offset=768)],
            ]
        )
        runner = _AckRunner(_make_transport())
        runner.run(
            sock,
            expected_cmd=CMD_UPLOAD_CHUNK,
            slave_id=3,
            offset=768,
        )

        self.assertEqual(3, len(sock.sends))
        self.assertEqual([0.1, 0.2], runner.sleeps)

    def test_ack_all_retries_exhausted(self) -> None:
        sock = _AckMockSocket([[None], [None], [None], [None]])
        runner = _AckRunner(_make_transport())

        with self.assertRaises(AckTimeoutError) as ctx:
            runner.run(
                sock,
                expected_cmd=CMD_UPLOAD_END,
                slave_id=5,
                offset=0,
            )

        exc = ctx.exception
        self.assertEqual(4, exc.attempts)
        self.assertEqual(CMD_UPLOAD_END, exc.acked_cmd)
        self.assertEqual(5, exc.slave_id)
        self.assertEqual(0, exc.offset)
        self.assertEqual(4, len(sock.sends))
        self.assertEqual([0.1, 0.2, 0.4], runner.sleeps)

    def test_ack_wrong_slave_id_ignored(self) -> None:
        sock = _AckMockSocket(
            [
                [
                    _ack(CMD_UPLOAD_BEGIN, slave_id=99),
                    _ack(CMD_UPLOAD_BEGIN, slave_id=7),
                ]
            ]
        )
        runner = _AckRunner(_make_transport())
        runner.run(sock, expected_cmd=CMD_UPLOAD_BEGIN, slave_id=7)

        self.assertEqual(1, len(sock.sends))
        self.assertEqual([], runner.sleeps)

    def test_ack_wrong_cmd_ignored(self) -> None:
        sock = _AckMockSocket(
            [
                [
                    _ack(CMD_UPLOAD_CHUNK, slave_id=7),
                    _ack(CMD_UPLOAD_BEGIN, slave_id=7),
                ]
            ]
        )
        runner = _AckRunner(_make_transport())
        runner.run(sock, expected_cmd=CMD_UPLOAD_BEGIN, slave_id=7)

        self.assertEqual(1, len(sock.sends))

    def test_ack_wrong_offset_ignored_for_chunk(self) -> None:
        sock = _AckMockSocket(
            [
                [
                    _ack(CMD_UPLOAD_CHUNK, slave_id=7, offset=0),
                    _ack(CMD_UPLOAD_CHUNK, slave_id=7, offset=768),
                ]
            ]
        )
        runner = _AckRunner(_make_transport())
        runner.run(
            sock,
            expected_cmd=CMD_UPLOAD_CHUNK,
            slave_id=7,
            offset=768,
        )

        self.assertEqual(1, len(sock.sends))

    def test_ack_wrong_magic_ignored(self) -> None:
        sock = _AckMockSocket(
            [
                [
                    _ack(CMD_UPLOAD_BEGIN, slave_id=7, magic=b"XXXX"),
                    _ack(CMD_UPLOAD_BEGIN, slave_id=7),
                ]
            ]
        )
        runner = _AckRunner(_make_transport())
        runner.run(sock, expected_cmd=CMD_UPLOAD_BEGIN, slave_id=7)

        self.assertEqual(1, len(sock.sends))

    def test_ack_custom_timeout_honored(self) -> None:
        sock = _AckMockSocket([[None]])
        runner = _AckRunner(
            _make_transport(
                ack_timeout_s=0.05,
                ack_max_retries=0,
                ack_backoff_delays=(),
            )
        )

        with self.assertRaises(AckTimeoutError):
            runner.run(sock, expected_cmd=CMD_UPLOAD_BEGIN, slave_id=7)

        self.assertEqual(1, len(sock.sends))
        self.assertEqual(1, len(runner.select_timeouts))
        first = runner.select_timeouts[0]
        self.assertIsNotNone(first)
        assert first is not None  # for mypy-like narrowing
        self.assertLessEqual(first, 0.05)
        self.assertGreater(first, 0.0)

    def test_ack_custom_backoff_honored(self) -> None:
        sock = _AckMockSocket(
            [
                [None],
                [None],
                [_ack(CMD_UPLOAD_BEGIN, slave_id=7)],
            ]
        )
        runner = _AckRunner(_make_transport(ack_backoff_delays=(0.01, 0.02, 0.04)))
        runner.run(sock, expected_cmd=CMD_UPLOAD_BEGIN, slave_id=7)

        self.assertEqual([0.01, 0.02], runner.sleeps)

    def test_ack_zero_max_retries(self) -> None:
        sock = _AckMockSocket([[None]])
        runner = _AckRunner(_make_transport(ack_max_retries=0))

        with self.assertRaises(AckTimeoutError) as ctx:
            runner.run(sock, expected_cmd=CMD_UPLOAD_BEGIN, slave_id=7)

        self.assertEqual(1, ctx.exception.attempts)
        self.assertEqual(1, len(sock.sends))
        self.assertEqual([], runner.sleeps)

    def test_ack_offset_zero_for_begin_end(self) -> None:
        sock = _AckMockSocket(
            [
                [_ack(CMD_UPLOAD_BEGIN, slave_id=7, offset=0)],
                [_ack(CMD_UPLOAD_END, slave_id=7, offset=0)],
            ]
        )
        runner = _AckRunner(_make_transport())
        runner.run(sock, expected_cmd=CMD_UPLOAD_BEGIN, slave_id=7)
        runner.run(sock, expected_cmd=CMD_UPLOAD_END, slave_id=7)

        self.assertEqual(2, len(sock.sends))
        self.assertEqual([], runner.sleeps)


if __name__ == "__main__":
    unittest.main()
