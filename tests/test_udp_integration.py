import math
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.compiled_show import (
    CompiledSlaveShow,
    CompileShowsForMastersUseCase,
)
from lightconductor.domain.models import Master, Slave, Tag, TagType
from lightconductor.infrastructure.master_udp_upload_transport import (
    MasterUdpUploadTransport,
)
from tests._mock_udp import (
    ParsedBegin,
    ParsedChunk,
    ParsedEnd,
    crc32_of,
    mock_udp_receiver,
    parse_packet,
    reassemble_blobs,
    start_packet_count,
)


def _build_master_with_slave(
    master_id="m1",
    master_ip="127.0.0.1",
    slave_id_str="s1",
    slave_pin="7",
    led_count=16,
    tag_type_pin="3",
    tag_count=2,
):
    """Build a minimal Master/Slave/TagType/Tag tree where every value is
    valid for compile. Returns a Master.
    """
    tags = []
    for i in range(tag_count):
        action = "On" if i % 2 == 0 else "Off"
        color_r = (i * 17) % 256
        color_g = (i * 29) % 256
        color_b = (i * 53) % 256
        tags.append(
            Tag(
                time_seconds=0.1 * (i + 1),
                action=action,
                colors=[[color_r, color_g, color_b]] * 4,
            )
        )
    tag_type = TagType(
        name="front",
        pin=tag_type_pin,
        rows=1,
        columns=4,
        topology=[0, 1, 2, 3],
        tags=tags,
    )
    slave = Slave(
        id=slave_id_str,
        name="slave",
        pin=slave_pin,
        led_count=led_count,
        tag_types={"front": tag_type},
    )
    return Master(
        id=master_id, name="master", ip=master_ip, slaves={slave_id_str: slave}
    )


def _drain_receiver(recv, expected_packet_count, timeout=1.0):
    """Spin-wait up to timeout for recv.packets to reach
    expected_packet_count. Loopback is fast but not zero-latency; this
    stabilizes CI.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with recv._lock:
            if len(recv.packets) >= expected_packet_count:
                return
        time.sleep(0.01)


def _compiled(
    slave_id: int, blob: bytes, master_ip: str = "127.0.0.1"
) -> CompiledSlaveShow:
    return CompiledSlaveShow(
        master_ip=master_ip,
        slave_id=slave_id,
        total_led_count=16,
        blob=blob,
    )


class UdpIntegrationTests(unittest.TestCase):
    def test_empty_upload_sends_nothing(self):
        with mock_udp_receiver() as recv:
            transport = MasterUdpUploadTransport(
                port=recv.port, inter_packet_delay=0.0, use_ack=False
            )
            transport.upload({})
            time.sleep(0.1)
            self.assertEqual([], recv.snapshot())

    def test_single_slave_small_blob_produces_begin_chunk_end(self):
        blob = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a"
        slave_id = 7
        with mock_udp_receiver() as recv:
            transport = MasterUdpUploadTransport(
                port=recv.port, chunk_size=1024, inter_packet_delay=0.0, use_ack=False
            )
            transport.upload({"127.0.0.1": [_compiled(slave_id, blob)]})
            _drain_receiver(recv, expected_packet_count=3)

        packets = recv.snapshot()
        self.assertEqual(3, len(packets))
        parsed = [parse_packet(p) for p in packets]
        self.assertIsInstance(parsed[0], ParsedBegin)
        self.assertIsInstance(parsed[1], ParsedChunk)
        self.assertIsInstance(parsed[2], ParsedEnd)
        self.assertEqual(slave_id, parsed[0].slave_id)
        self.assertEqual(slave_id, parsed[1].slave_id)
        self.assertEqual(slave_id, parsed[2].slave_id)

    def test_large_blob_splits_into_multiple_chunks(self):
        chunk_size = 32
        blob = bytes(range(256)) * 2  # 512 bytes -> 16 chunks of 32
        slave_id = 12
        expected_chunks = math.ceil(len(blob) / chunk_size)
        expected_total = 1 + expected_chunks + 1

        with mock_udp_receiver() as recv:
            transport = MasterUdpUploadTransport(
                port=recv.port,
                chunk_size=chunk_size,
                inter_packet_delay=0.0,
                use_ack=False,
            )
            transport.upload({"127.0.0.1": [_compiled(slave_id, blob)]})
            _drain_receiver(recv, expected_packet_count=expected_total)

        packets = recv.snapshot()
        parsed = [parse_packet(p) for p in packets]
        begins = [p for p in parsed if isinstance(p, ParsedBegin)]
        chunks = [p for p in parsed if isinstance(p, ParsedChunk)]
        ends = [p for p in parsed if isinstance(p, ParsedEnd)]
        self.assertEqual(1, len(begins))
        self.assertEqual(1, len(ends))
        self.assertEqual(expected_chunks, len(chunks))

        reassembled = reassemble_blobs(packets)
        self.assertIn(slave_id, reassembled)
        self.assertEqual(blob, reassembled[slave_id])

    def test_begin_packet_carries_correct_total_size_and_crc(self):
        blob = b"LightConductor-test-blob-payload"
        slave_id = 42
        with mock_udp_receiver() as recv:
            transport = MasterUdpUploadTransport(
                port=recv.port, chunk_size=1024, inter_packet_delay=0.0, use_ack=False
            )
            transport.upload({"127.0.0.1": [_compiled(slave_id, blob)]})
            _drain_receiver(recv, expected_packet_count=3)

        packets = recv.snapshot()
        begins = [
            parse_packet(p) for p in packets if isinstance(parse_packet(p), ParsedBegin)
        ]
        self.assertEqual(1, len(begins))
        begin = begins[0]
        self.assertEqual(len(blob), begin.total_size)
        self.assertEqual(crc32_of(blob), begin.crc32)

    def test_chunk_offsets_are_sequential_and_cover_blob(self):
        chunk_size = 64
        blob = bytes((i * 7) & 0xFF for i in range(200))  # 200 bytes
        slave_id = 3
        expected_chunks = math.ceil(len(blob) / chunk_size)
        expected_total = 1 + expected_chunks + 1

        with mock_udp_receiver() as recv:
            transport = MasterUdpUploadTransport(
                port=recv.port,
                chunk_size=chunk_size,
                inter_packet_delay=0.0,
                use_ack=False,
            )
            transport.upload({"127.0.0.1": [_compiled(slave_id, blob)]})
            _drain_receiver(recv, expected_packet_count=expected_total)

        packets = recv.snapshot()
        parsed = [parse_packet(p) for p in packets]
        chunks = sorted(
            [p for p in parsed if isinstance(p, ParsedChunk)],
            key=lambda c: c.offset,
        )
        self.assertEqual(expected_chunks, len(chunks))
        self.assertEqual(0, chunks[0].offset)
        for prev, cur in zip(chunks, chunks[1:], strict=False):
            self.assertEqual(prev.offset + chunk_size, cur.offset)
            self.assertEqual(chunk_size, prev.chunk_len)
        self.assertEqual(len(blob), sum(c.chunk_len for c in chunks))

    def test_two_slaves_same_host_upload_all_blobs(self):
        blob_a = b"alpha-blob-" * 3
        blob_b = b"bravo-blob-" * 4
        slave_a, slave_b = 10, 20
        with mock_udp_receiver() as recv:
            transport = MasterUdpUploadTransport(
                port=recv.port, chunk_size=1024, inter_packet_delay=0.0, use_ack=False
            )
            transport.upload(
                {
                    "127.0.0.1": [
                        _compiled(slave_a, blob_a),
                        _compiled(slave_b, blob_b),
                    ]
                }
            )
            _drain_receiver(recv, expected_packet_count=6)

        packets = recv.snapshot()
        reassembled = reassemble_blobs(packets)
        self.assertIn(slave_a, reassembled)
        self.assertIn(slave_b, reassembled)
        self.assertEqual(blob_a, reassembled[slave_a])
        self.assertEqual(blob_b, reassembled[slave_b])

    def test_two_masters_different_hosts_are_both_targeted(self):
        # Two distinct dict keys both resolve to loopback so the single
        # mock receiver captures packets from both. This exercises the
        # outer (host) loop in upload().
        blob_a = b"master-a-payload"
        blob_b = b"master-b-payload"
        slave_a, slave_b = 11, 22
        with mock_udp_receiver() as recv:
            transport = MasterUdpUploadTransport(
                port=recv.port, chunk_size=1024, inter_packet_delay=0.0, use_ack=False
            )
            transport.upload(
                {
                    "127.0.0.1": [_compiled(slave_a, blob_a)],
                    "localhost": [_compiled(slave_b, blob_b)],
                }
            )
            _drain_receiver(recv, expected_packet_count=6)

        packets = recv.snapshot()
        parsed = [parse_packet(p) for p in packets]
        begins = [p for p in parsed if isinstance(p, ParsedBegin)]
        ends = [p for p in parsed if isinstance(p, ParsedEnd)]
        self.assertEqual(2, len(begins))
        self.assertEqual(2, len(ends))
        begin_slaves = {b.slave_id for b in begins}
        self.assertEqual({slave_a, slave_b}, begin_slaves)

    def test_start_show_with_distinct_hosts_deduplicates(self):
        with mock_udp_receiver() as recv:
            transport = MasterUdpUploadTransport(
                port=recv.port, inter_packet_delay=0.0, use_ack=False
            )
            transport.start_show(["127.0.0.1", "127.0.0.1", "127.0.0.1"])
            _drain_receiver(recv, expected_packet_count=1)
            time.sleep(0.1)

        packets = recv.snapshot()
        self.assertEqual(1, len(packets))
        self.assertEqual(1, start_packet_count(packets))

    def test_start_show_empty_hosts_sends_nothing(self):
        with mock_udp_receiver() as recv:
            transport = MasterUdpUploadTransport(
                port=recv.port, inter_packet_delay=0.0, use_ack=False
            )
            transport.start_show([])
            time.sleep(0.1)
            self.assertEqual([], recv.snapshot())

    def test_full_pipeline_from_compile_to_wire(self):
        master = _build_master_with_slave(
            master_ip="127.0.0.1",
            slave_pin="7",
            led_count=16,
            tag_type_pin="3",
            tag_count=2,
        )
        compiled_by_host = CompileShowsForMastersUseCase().execute({"m1": master})
        show = compiled_by_host["127.0.0.1"][0]
        source_blob = show.blob
        source_slave_id = show.slave_id

        with mock_udp_receiver() as recv:
            transport = MasterUdpUploadTransport(
                port=recv.port, chunk_size=1024, inter_packet_delay=0.0, use_ack=False
            )
            transport.upload(compiled_by_host)
            _drain_receiver(recv, expected_packet_count=3)

        packets = recv.snapshot()
        reassembled = reassemble_blobs(packets)
        self.assertIn(source_slave_id, reassembled)
        self.assertEqual(source_blob, reassembled[source_slave_id])

        begins = [
            parse_packet(p) for p in packets if isinstance(parse_packet(p), ParsedBegin)
        ]
        self.assertEqual(1, len(begins))
        self.assertEqual(crc32_of(source_blob), begins[0].crc32)
        self.assertEqual(len(source_blob), begins[0].total_size)


if __name__ == "__main__":
    unittest.main()
