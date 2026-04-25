"""Phase 17.2 integration tests: upload() wired to _send_with_ack.

These tests exercise :class:`MasterUdpUploadTransport.upload` end-to-end
with ACK-enabled delivery (the new default in 17.2). ``select.select``
and ``time.sleep`` are patched at module scope on the transport module
so every test runs in milliseconds irrespective of configured ACK
timeouts and backoff schedules.

The companion file ``tests/test_master_udp_ack.py`` still exercises
``_send_with_ack`` in isolation (17.1 baseline, unchanged).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.compiled_show import CompiledSlaveShow
from lightconductor.infrastructure import master_udp_upload_transport as mut
from lightconductor.infrastructure.master_udp_upload_transport import (
    ACK_STRUCT,
    APP_MAGIC,
    BEGIN_STRUCT,
    CHUNK_HEAD_STRUCT,
    CMD_ACK,
    CMD_UPLOAD_BEGIN,
    CMD_UPLOAD_CHUNK,
    CMD_UPLOAD_END,
    END_STRUCT,
    AckTimeoutError,
    MasterUdpUploadTransport,
    UploadFailedError,
    count_upload_packets,
)

ADDR: Tuple[str, int] = ("10.0.0.1", 43690)


def _compiled(slave_id: int, blob: bytes, host: str = "10.0.0.1") -> CompiledSlaveShow:
    return CompiledSlaveShow(
        master_ip=host,
        slave_id=slave_id,
        total_led_count=16,
        blob=blob,
    )


def _ack_for(data: bytes) -> Optional[bytes]:
    """Build the CMD_ACK packet a master firmware-v6 would emit for a
    given upload packet. Returns None for packets we don't recognise.
    """
    if len(data) < 5 or data[:4] != APP_MAGIC:
        return None
    cmd = data[4]
    if cmd == CMD_UPLOAD_BEGIN and len(data) == BEGIN_STRUCT.size:
        _m, _c, slave_id, _size, _crc = BEGIN_STRUCT.unpack(data)
        return ACK_STRUCT.pack(APP_MAGIC, CMD_ACK, CMD_UPLOAD_BEGIN, slave_id, 0)
    if cmd == CMD_UPLOAD_CHUNK and len(data) >= CHUNK_HEAD_STRUCT.size:
        _m, _c, slave_id, offset, _len = CHUNK_HEAD_STRUCT.unpack(
            data[: CHUNK_HEAD_STRUCT.size]
        )
        return ACK_STRUCT.pack(APP_MAGIC, CMD_ACK, CMD_UPLOAD_CHUNK, slave_id, offset)
    if cmd == CMD_UPLOAD_END and len(data) == END_STRUCT.size:
        _m, _c, slave_id = END_STRUCT.unpack(data)
        return ACK_STRUCT.pack(APP_MAGIC, CMD_ACK, CMD_UPLOAD_END, slave_id, 0)
    return None


class _UploadMockSocket:
    """Test double for the UDP socket used by ``upload()`` under the
    ACK path.

    ``drop_plan[i] = True`` drops the i-th sendto (the mock master
    stays silent, forcing the transport to retry). False means the
    mock master auto-ACKs the send. When ``drop_plan`` is exhausted,
    subsequent sends are auto-ACKed.
    """

    def __init__(self, drop_plan: Optional[List[bool]] = None) -> None:
        self.sends: List[Tuple[bytes, Tuple[str, int]]] = []
        self._drop_plan: List[bool] = list(drop_plan or [])
        self._drop_idx = 0
        self._pending: List[Optional[bytes]] = []
        self.closed = False

    def sendto(self, data: bytes, addr: Tuple[str, int]) -> int:
        self.sends.append((bytes(data), addr))
        drop = False
        if self._drop_idx < len(self._drop_plan):
            drop = self._drop_plan[self._drop_idx]
            self._drop_idx += 1
        if drop:
            self._pending = [None]
        else:
            self._pending = [_ack_for(data)]
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


def _make_mock_socket_factory(
    drop_plan: Optional[List[bool]] = None,
) -> Callable[[], _UploadMockSocket]:
    """Return a factory producing a single ``_UploadMockSocket`` per
    call. Exposes ``.sockets`` on the callable for assertions.
    """
    sockets: List[_UploadMockSocket] = []

    def factory() -> _UploadMockSocket:
        s = _UploadMockSocket(drop_plan=drop_plan)
        sockets.append(s)
        return s

    factory.sockets = sockets  # type: ignore[attr-defined]
    return factory


def _fake_select(
    rlist: List[object],
    wlist: List[object],
    xlist: List[object],
    timeout: Optional[float] = None,
) -> Tuple[List[object], List[object], List[object]]:
    for s in rlist:
        if hasattr(s, "_has_data") and s._has_data():  # type: ignore[attr-defined]
            return ([s], [], [])
    return ([], [], [])


def _make_transport(
    factory: Callable[[], _UploadMockSocket],
    *,
    chunk_size: int = 10,
    use_ack: bool = True,
    ack_max_retries: int = 3,
    ack_backoff_delays: Tuple[float, ...] = (0.0, 0.0, 0.0),
) -> MasterUdpUploadTransport:
    return MasterUdpUploadTransport(
        port=43690,
        chunk_size=chunk_size,
        inter_packet_delay=0.0,
        max_retries=0,
        retry_base_delay=0.0,
        socket_factory=factory,
        ack_timeout_s=0.01,
        ack_max_retries=ack_max_retries,
        ack_backoff_delays=ack_backoff_delays,
        use_ack=use_ack,
    )


class UploadAckIntegrationTests(unittest.TestCase):
    def _run_upload(
        self,
        transport: MasterUdpUploadTransport,
        compiled: dict,
    ) -> None:
        with (
            mock.patch.object(mut.select, "select", side_effect=_fake_select),
            mock.patch.object(mut.time, "sleep", side_effect=lambda _d: None),
        ):
            transport.upload(compiled)

    def test_upload_all_acks_succeed(self) -> None:
        """Auto-ACK on every send -> upload() returns cleanly with one
        sendto per upload packet (no retries).
        """
        factory = _make_mock_socket_factory()
        transport = _make_transport(factory, chunk_size=4)
        # 8-byte blob -> 2 chunks of 4 -> BEGIN + 2 CHUNK + END = 4 sends.
        blob = b"\x01\x02\x03\x04\x05\x06\x07\x08"
        self._run_upload(transport, {ADDR[0]: [_compiled(7, blob)]})

        sock = factory.sockets[0]  # type: ignore[attr-defined]
        self.assertEqual(4, len(sock.sends))
        cmds = [pkt[4] for pkt, _ in sock.sends]
        self.assertEqual(
            [CMD_UPLOAD_BEGIN, CMD_UPLOAD_CHUNK, CMD_UPLOAD_CHUNK, CMD_UPLOAD_END],
            cmds,
        )
        self.assertTrue(sock.closed)

    def test_upload_one_chunk_retry(self) -> None:
        """Drop the first CHUNK send; the retry is ACKed and upload()
        succeeds. Total sends = N + 1.
        """
        # Plan per-send: BEGIN=ok, CHUNK_try1=drop, CHUNK_try2=ok, END=ok.
        factory = _make_mock_socket_factory(drop_plan=[False, True, False, False])
        transport = _make_transport(factory, chunk_size=10)
        blob = b"abcdefghij"  # exactly one chunk.
        self._run_upload(transport, {ADDR[0]: [_compiled(3, blob)]})

        sock = factory.sockets[0]  # type: ignore[attr-defined]
        # BEGIN + CHUNK (try1 dropped) + CHUNK (retry) + END = 4 sends.
        self.assertEqual(4, len(sock.sends))
        # The 2nd and 3rd sends are both CHUNK packets for the same
        # offset=0 -- proves a retry, not a fresh chunk.
        self.assertEqual(CMD_UPLOAD_CHUNK, sock.sends[1][0][4])
        self.assertEqual(CMD_UPLOAD_CHUNK, sock.sends[2][0][4])
        _, _, _, offset2, _ = CHUNK_HEAD_STRUCT.unpack(
            sock.sends[1][0][: CHUNK_HEAD_STRUCT.size]
        )
        _, _, _, offset3, _ = CHUNK_HEAD_STRUCT.unpack(
            sock.sends[2][0][: CHUNK_HEAD_STRUCT.size]
        )
        self.assertEqual(0, offset2)
        self.assertEqual(0, offset3)

    def test_upload_begin_timeout(self) -> None:
        """Master never ACKs the BEGIN for the second slave. After all
        ACK retries are exhausted, AckTimeoutError propagates -- which
        is a subclass of UploadFailedError. Earlier-slave sends still
        happened before the failure.
        """
        # Slave 7: BEGIN ok, CHUNK ok, END ok (3 sends).
        # Slave 8: BEGIN dropped x (1 + ack_max_retries=3) = 4 sends.
        factory = _make_mock_socket_factory(
            drop_plan=[False, False, False, True, True, True, True]
        )
        transport = _make_transport(factory, chunk_size=4, ack_max_retries=3)
        blob = b"abcd"  # exactly one chunk for slave 7.

        with self.assertRaises(UploadFailedError) as ctx:
            self._run_upload(
                transport,
                {
                    ADDR[0]: [
                        _compiled(7, blob),
                        _compiled(8, blob),
                    ]
                },
            )

        self.assertIsInstance(ctx.exception, AckTimeoutError)
        err = ctx.exception
        assert isinstance(err, AckTimeoutError)
        self.assertEqual(CMD_UPLOAD_BEGIN, err.acked_cmd)
        self.assertEqual(8, err.slave_id)
        self.assertEqual(4, err.attempts)

        sock = factory.sockets[0]  # type: ignore[attr-defined]
        # 3 sends for slave 7 + 4 timeout attempts for slave 8 BEGIN.
        self.assertEqual(7, len(sock.sends))
        # Slave 7's END was sent (proves partial progress).
        cmds_slave7 = [pkt[4] for pkt, _ in sock.sends[:3]]
        self.assertIn(CMD_UPLOAD_END, cmds_slave7)

    def test_upload_end_timeout(self) -> None:
        """BEGIN and all CHUNKs ACK; END never does -> raises."""
        # BEGIN=ok, CHUNK=ok, END_tryN=drop (4 times for 1 + retries=3).
        factory = _make_mock_socket_factory(
            drop_plan=[False, False, True, True, True, True]
        )
        transport = _make_transport(factory, chunk_size=4, ack_max_retries=3)
        blob = b"abcd"

        with self.assertRaises(UploadFailedError) as ctx:
            self._run_upload(transport, {ADDR[0]: [_compiled(9, blob)]})

        self.assertIsInstance(ctx.exception, AckTimeoutError)
        err = ctx.exception
        assert isinstance(err, AckTimeoutError)
        self.assertEqual(CMD_UPLOAD_END, err.acked_cmd)
        self.assertEqual(9, err.slave_id)
        self.assertEqual(4, err.attempts)

        sock = factory.sockets[0]  # type: ignore[attr-defined]
        # BEGIN + CHUNK + 4 END attempts = 6 sends.
        self.assertEqual(6, len(sock.sends))

    def test_upload_start_show_no_ack(self) -> None:
        """start_show() is fire-and-forget: the mock master sends no
        ACK yet start_show returns cleanly. Documents the wire-protocol
        invariant that CMD_START_SHOW is unacknowledged by design.
        """
        factory = _make_mock_socket_factory()
        transport = _make_transport(factory, chunk_size=4)
        # No select/sleep patching needed -- start_show uses the legacy
        # retry path, never enters the ACK wait loop.
        transport.start_show([ADDR[0]])

        sock = factory.sockets[0]  # type: ignore[attr-defined]
        self.assertEqual(1, len(sock.sends))
        self.assertTrue(sock.closed)

    def test_use_ack_false_uses_legacy_path(self) -> None:
        """With use_ack=False, upload() never calls _send_with_ack.
        The mock master does not ACK anything; upload still completes
        because the legacy path only cares about sendto success.
        """
        factory = _make_mock_socket_factory()
        transport = _make_transport(factory, chunk_size=4, use_ack=False)
        blob = b"abcdefgh"  # 2 chunks.

        # Deliberately do NOT patch select/sleep: the legacy path
        # must not touch either. If the transport regresses into the
        # ACK path, this test would hang and eventually fail the CI
        # timeout (or call the real select, which returns no data).
        transport.upload({ADDR[0]: [_compiled(5, blob)]})

        sock = factory.sockets[0]  # type: ignore[attr-defined]
        # BEGIN + 2 CHUNK + END = 4 sends, no retries.
        self.assertEqual(4, len(sock.sends))
        cmds = [pkt[4] for pkt, _ in sock.sends]
        self.assertEqual(
            [CMD_UPLOAD_BEGIN, CMD_UPLOAD_CHUNK, CMD_UPLOAD_CHUNK, CMD_UPLOAD_END],
            cmds,
        )


class ChunkRedundancy(unittest.TestCase):
    """Phase 19.1 — per-chunk UART-redundancy tests.

    The transport is constructed with ``use_ack=False`` by default
    here so the assertions on raw sendto counts/offsets stay
    unmuddied by ACK retries. ``test_ack_retry_inside_redundancy_attempt``
    explicitly exercises the ACK path.
    """

    def _run(
        self,
        transport: MasterUdpUploadTransport,
        compiled: dict,
        *,
        progress_callback: Optional[Callable[[int, int], bool]] = None,
        patch_select: bool = False,
    ) -> None:
        if patch_select:
            with (
                mock.patch.object(mut.select, "select", side_effect=_fake_select),
                mock.patch.object(mut.time, "sleep", side_effect=lambda _d: None),
            ):
                transport.upload(compiled, progress_callback=progress_callback)
        else:
            with mock.patch.object(mut.time, "sleep", side_effect=lambda _d: None):
                transport.upload(compiled, progress_callback=progress_callback)

    def _make_no_ack_transport(
        self,
        factory: Callable[[], _UploadMockSocket],
        *,
        chunk_size: int = 4,
        chunk_redundancy: int = 1,
    ) -> MasterUdpUploadTransport:
        return MasterUdpUploadTransport(
            port=43690,
            chunk_size=chunk_size,
            inter_packet_delay=0.0,
            max_retries=0,
            retry_base_delay=0.0,
            socket_factory=factory,
            use_ack=False,
            chunk_redundancy=chunk_redundancy,
        )

    def test_redundancy_1_is_default_and_matches_current_behavior(self) -> None:
        factory = _make_mock_socket_factory()
        transport = self._make_no_ack_transport(factory, chunk_size=4)
        # Default: no chunk_redundancy passed -> 1.
        self.assertEqual(1, transport.chunk_redundancy)
        # 12-byte blob -> 3 chunks of 4 -> BEGIN + 3 CHUNK + END = 5 sends.
        blob = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c"
        self._run(transport, {ADDR[0]: [_compiled(7, blob)]})

        sock = factory.sockets[0]  # type: ignore[attr-defined]
        self.assertEqual(5, len(sock.sends))
        cmds = [pkt[4] for pkt, _ in sock.sends]
        self.assertEqual(
            [
                CMD_UPLOAD_BEGIN,
                CMD_UPLOAD_CHUNK,
                CMD_UPLOAD_CHUNK,
                CMD_UPLOAD_CHUNK,
                CMD_UPLOAD_END,
            ],
            cmds,
        )

    def test_redundancy_2_sends_each_chunk_twice(self) -> None:
        factory = _make_mock_socket_factory()
        transport = self._make_no_ack_transport(
            factory, chunk_size=4, chunk_redundancy=2
        )
        blob = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c"
        self._run(transport, {ADDR[0]: [_compiled(7, blob)]})

        sock = factory.sockets[0]  # type: ignore[attr-defined]
        # BEGIN + 3*2 CHUNK + END = 8 sends.
        self.assertEqual(8, len(sock.sends))
        cmds = [pkt[4] for pkt, _ in sock.sends]
        # BEGIN sent exactly once.
        self.assertEqual(1, cmds.count(CMD_UPLOAD_BEGIN))
        # END sent exactly once.
        self.assertEqual(1, cmds.count(CMD_UPLOAD_END))
        # 6 CHUNK sends in the middle.
        self.assertEqual(6, cmds.count(CMD_UPLOAD_CHUNK))
        # Order: BEGIN first, END last, all 6 CHUNK in between.
        self.assertEqual(CMD_UPLOAD_BEGIN, cmds[0])
        self.assertEqual(CMD_UPLOAD_END, cmds[-1])
        self.assertTrue(all(c == CMD_UPLOAD_CHUNK for c in cmds[1:-1]))
        # Offsets of the six chunk sends: [0, 0, 4, 4, 8, 8].
        offsets: List[int] = []
        for pkt, _ in sock.sends[1:-1]:
            _m, _c, _sid, off, _ln = CHUNK_HEAD_STRUCT.unpack(
                pkt[: CHUNK_HEAD_STRUCT.size]
            )
            offsets.append(off)
        self.assertEqual([0, 0, 4, 4, 8, 8], offsets)

    def test_redundancy_3_sends_each_chunk_thrice(self) -> None:
        factory = _make_mock_socket_factory()
        transport = self._make_no_ack_transport(
            factory, chunk_size=4, chunk_redundancy=3
        )
        # 8-byte blob -> 2 chunks. BEGIN + 2*3 CHUNK + END = 8 sends.
        blob = b"abcdefgh"
        self._run(transport, {ADDR[0]: [_compiled(7, blob)]})

        sock = factory.sockets[0]  # type: ignore[attr-defined]
        self.assertEqual(8, len(sock.sends))
        cmds = [pkt[4] for pkt, _ in sock.sends]
        self.assertEqual(1, cmds.count(CMD_UPLOAD_BEGIN))
        self.assertEqual(1, cmds.count(CMD_UPLOAD_END))
        self.assertEqual(6, cmds.count(CMD_UPLOAD_CHUNK))

    def test_redundancy_zero_clamped_to_one(self) -> None:
        transport = MasterUdpUploadTransport(chunk_redundancy=0)
        self.assertEqual(1, transport.chunk_redundancy)

    def test_redundancy_negative_clamped_to_one(self) -> None:
        transport = MasterUdpUploadTransport(chunk_redundancy=-5)
        self.assertEqual(1, transport.chunk_redundancy)

    def test_progress_callback_counts_each_redundancy_send(self) -> None:
        factory = _make_mock_socket_factory()
        transport = self._make_no_ack_transport(
            factory, chunk_size=4, chunk_redundancy=2
        )
        blob = b"abcdefgh"  # 2 chunks.
        observed: List[Tuple[int, int]] = []

        def callback(sent: int, total: int) -> bool:
            observed.append((sent, total))
            return True

        self._run(
            transport,
            {ADDR[0]: [_compiled(7, blob)]},
            progress_callback=callback,
        )

        # Total = BEGIN + 2*2 CHUNK + END = 6.
        self.assertEqual(
            [(1, 6), (2, 6), (3, 6), (4, 6), (5, 6), (6, 6)],
            observed,
        )

    def test_ack_retry_inside_redundancy_attempt(self) -> None:
        """N=2; first ACK for the first redundancy copy of chunk@0 is
        dropped. The transport's internal ACK-retry recovers within
        that single redundancy attempt; the second redundancy copy
        proceeds normally; END is reached and the upload completes.
        """
        # Drop plan per send (in order): BEGIN ok, CHUNK#1-try1 drop,
        # CHUNK#1-try2 ok (ACK-retry recovers), CHUNK#1-redundant-copy
        # ok, END ok = 5 mock-master events.
        factory = _make_mock_socket_factory(
            drop_plan=[False, True, False, False, False]
        )
        transport = MasterUdpUploadTransport(
            port=43690,
            chunk_size=10,
            inter_packet_delay=0.0,
            max_retries=0,
            retry_base_delay=0.0,
            socket_factory=factory,
            ack_timeout_s=0.01,
            ack_max_retries=3,
            ack_backoff_delays=(0.0, 0.0, 0.0),
            use_ack=True,
            chunk_redundancy=2,
        )
        blob = b"abcdefghij"  # exactly one chunk.
        self._run(
            transport,
            {ADDR[0]: [_compiled(3, blob)]},
            patch_select=True,
        )

        sock = factory.sockets[0]  # type: ignore[attr-defined]
        # BEGIN + (CHUNK try1 dropped + CHUNK retry) + CHUNK redundant + END
        # = 5 sendto calls total.
        self.assertEqual(5, len(sock.sends))
        cmds = [pkt[4] for pkt, _ in sock.sends]
        self.assertEqual(
            [
                CMD_UPLOAD_BEGIN,
                CMD_UPLOAD_CHUNK,  # first redundancy copy, ACK dropped
                CMD_UPLOAD_CHUNK,  # ACK retry of the same copy
                CMD_UPLOAD_CHUNK,  # second redundancy copy
                CMD_UPLOAD_END,
            ],
            cmds,
        )
        # All three CHUNK sends carry offset=0.
        for i in (1, 2, 3):
            _m, _c, _sid, off, _ln = CHUNK_HEAD_STRUCT.unpack(
                sock.sends[i][0][: CHUNK_HEAD_STRUCT.size]
            )
            self.assertEqual(0, off)

    def test_count_upload_packets_redundancy_keyword(self) -> None:
        compiled = {
            ADDR[0]: [
                _compiled(1, b"x" * 10),  # 4 chunks @ chunk_size=3
                _compiled(2, b"x" * 6),   # 2 chunks
            ],
        }
        # Default redundancy=1: per slave 2 + chunks. (2+4) + (2+2) = 10.
        self.assertEqual(10, count_upload_packets(compiled, 3))
        # redundancy=3: 2 + chunks*3. (2+12) + (2+6) = 22.
        self.assertEqual(
            22, count_upload_packets(compiled, 3, chunk_redundancy=3)
        )
        # Non-positive coerces to 1.
        self.assertEqual(
            10, count_upload_packets(compiled, 3, chunk_redundancy=0)
        )
        self.assertEqual(
            10, count_upload_packets(compiled, 3, chunk_redundancy=-2)
        )


if __name__ == "__main__":
    unittest.main()
