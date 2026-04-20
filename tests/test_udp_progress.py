import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.compiled_show import (
    CompiledSlaveShow,
)
from lightconductor.infrastructure.master_udp_upload_transport import (
    MasterUdpUploadTransport,
    UploadCancelledError,
    count_upload_packets,
)
from tests._mock_udp import (
    make_failing_socket_factory,
)


def _make_compiled(host="10.0.0.1", slave_id=7, blob=b"abc"):
    return {
        host: [
            CompiledSlaveShow(
                master_ip=host,
                slave_id=slave_id,
                total_led_count=16,
                blob=blob,
            )
        ]
    }


class CountUploadPacketsTests(unittest.TestCase):
    def test_count_empty_input_zero(self):
        self.assertEqual(0, count_upload_packets({}, 100))

    def test_count_single_small_blob(self):
        compiled = {
            "h": [
                CompiledSlaveShow(
                    master_ip="h",
                    slave_id=1,
                    total_led_count=4,
                    blob=b"ab",
                )
            ]
        }
        # BEGIN + 1 chunk + END = 3
        self.assertEqual(3, count_upload_packets(compiled, 100))

    def test_count_large_blob_splits_chunks(self):
        compiled = {
            "h": [
                CompiledSlaveShow(
                    master_ip="h",
                    slave_id=1,
                    total_led_count=4,
                    blob=b"a" * 250,
                )
            ]
        }
        # 250 / 100 -> 3 chunks -> 2 + 3 = 5
        self.assertEqual(5, count_upload_packets(compiled, 100))

    def test_count_empty_blob_two_packets(self):
        compiled = {
            "h": [
                CompiledSlaveShow(
                    master_ip="h",
                    slave_id=1,
                    total_led_count=4,
                    blob=b"",
                )
            ]
        }
        # BEGIN + 0 chunks + END = 2
        self.assertEqual(2, count_upload_packets(compiled, 100))

    def test_count_multi_host_multi_slave_aggregates(self):
        compiled = {
            "h1": [
                CompiledSlaveShow(
                    master_ip="h1",
                    slave_id=1,
                    total_led_count=4,
                    blob=b"a" * 50,
                ),
                CompiledSlaveShow(
                    master_ip="h1",
                    slave_id=2,
                    total_led_count=4,
                    blob=b"a" * 150,
                ),
            ],
            "h2": [
                CompiledSlaveShow(
                    master_ip="h2",
                    slave_id=3,
                    total_led_count=4,
                    blob=b"",
                ),
                CompiledSlaveShow(
                    master_ip="h2",
                    slave_id=4,
                    total_led_count=4,
                    blob=b"a" * 100,
                ),
            ],
        }
        # h1: (2+1) + (2+2) = 7
        # h2: (2+0) + (2+1) = 5
        # total = 12
        self.assertEqual(12, count_upload_packets(compiled, 100))


class UploadProgressCallbackTests(unittest.TestCase):
    def _transport(self, factory):
        return MasterUdpUploadTransport(
            port=43690,
            chunk_size=10,
            inter_packet_delay=0.0,
            max_retries=0,
            retry_base_delay=0.0,
            socket_factory=factory,
        )

    def test_callback_invoked_once_per_successful_send(self):
        factory = make_failing_socket_factory([])
        transport = self._transport(factory)
        recorded = []

        def cb(sent, total):
            recorded.append((sent, total))
            return True

        transport.upload(
            _make_compiled(blob=b"abc"),
            progress_callback=cb,
        )

        self.assertEqual([(1, 3), (2, 3), (3, 3)], recorded)
        sock = factory.sockets[0]
        self.assertEqual(3, sock.attempt_count)

    def test_callback_return_false_raises_cancelled_error(self):
        factory = make_failing_socket_factory([])
        transport = self._transport(factory)
        recorded = []

        def cb(sent, total):
            recorded.append((sent, total))
            return sent < 2  # False on the 2nd call

        with self.assertRaises(UploadCancelledError) as ctx:
            transport.upload(
                _make_compiled(blob=b"abc"),
                progress_callback=cb,
            )

        self.assertEqual(2, ctx.exception.packets_sent)
        self.assertEqual(3, ctx.exception.total_packets)
        sock = factory.sockets[0]
        # Cancel stops BEFORE the END send.
        self.assertEqual(2, len(sock.record))

    def test_cancel_on_very_first_call_stops_after_one_packet(self):
        factory = make_failing_socket_factory([])
        transport = self._transport(factory)

        def cb(sent, total):
            return False

        with self.assertRaises(UploadCancelledError) as ctx:
            transport.upload(
                _make_compiled(blob=b"abc"),
                progress_callback=cb,
            )

        self.assertEqual(1, ctx.exception.packets_sent)
        self.assertEqual(3, ctx.exception.total_packets)
        sock = factory.sockets[0]
        self.assertEqual(1, len(sock.record))

    def test_callback_none_equals_silent_upload(self):
        factory = make_failing_socket_factory([])
        transport = self._transport(factory)

        transport.upload(_make_compiled(blob=b"abc"))

        sock = factory.sockets[0]
        self.assertEqual(3, sock.attempt_count)

    def test_start_show_drives_callback(self):
        factory = make_failing_socket_factory([])
        transport = MasterUdpUploadTransport(
            port=43690,
            inter_packet_delay=0.0,
            max_retries=0,
            retry_base_delay=0.0,
            socket_factory=factory,
        )
        recorded = []

        def cb(sent, total):
            recorded.append((sent, total))
            return True

        transport.start_show(
            ["10.0.0.1", "10.0.0.2"],
            progress_callback=cb,
        )

        self.assertEqual([(1, 2), (2, 2)], recorded)

        # Second call: cancel on first callback.
        factory2 = make_failing_socket_factory([])
        transport2 = MasterUdpUploadTransport(
            port=43690,
            inter_packet_delay=0.0,
            max_retries=0,
            retry_base_delay=0.0,
            socket_factory=factory2,
        )

        def cancel_cb(sent, total):
            return False

        with self.assertRaises(UploadCancelledError) as ctx:
            transport2.start_show(
                ["10.0.0.1", "10.0.0.2"],
                progress_callback=cancel_cb,
            )

        self.assertEqual(1, ctx.exception.packets_sent)
        self.assertEqual(2, ctx.exception.total_packets)


if __name__ == "__main__":
    unittest.main()
