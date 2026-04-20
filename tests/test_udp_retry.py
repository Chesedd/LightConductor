import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.compiled_show import CompiledSlaveShow
from lightconductor.infrastructure.master_udp_upload_transport import (
    MasterUdpUploadTransport,
    UploadFailedError,
    compute_backoff_delays,
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


class ComputeBackoffDelaysTests(unittest.TestCase):
    def test_zero_max_retries_returns_empty_list(self):
        self.assertEqual([], compute_backoff_delays(0, 0.05, 1.0))

    def test_default_sequence_doubles_capped_at_max(self):
        self.assertEqual(
            [0.05, 0.10, 0.20, 0.40, 0.80],
            compute_backoff_delays(5, 0.05, 1.0),
        )

    def test_cap_applies_when_exceeded(self):
        self.assertEqual(
            [0.5, 1.0, 1.0, 1.0, 1.0],
            compute_backoff_delays(5, 0.5, 1.0),
        )

    def test_negative_max_retries_clamped_to_zero(self):
        self.assertEqual([], compute_backoff_delays(-3, 0.05, 1.0))

    def test_zero_base_delay_returns_zeros(self):
        self.assertEqual([0.0, 0.0, 0.0], compute_backoff_delays(3, 0.0, 1.0))

    def test_negative_inputs_clamped(self):
        self.assertEqual([0.0, 0.0], compute_backoff_delays(2, -0.5, -1.0))


class UploadRetryBehaviourTests(unittest.TestCase):
    def test_upload_succeeds_first_attempt_no_retry_logs(self):
        factory = make_failing_socket_factory([])
        transport = MasterUdpUploadTransport(
            port=43690,
            chunk_size=1024,
            inter_packet_delay=0.0,
            max_retries=2,
            retry_base_delay=0.0,
            socket_factory=factory,
        )
        transport.upload(_make_compiled(blob=b"abc"))

        self.assertEqual(1, len(factory.sockets))
        sock = factory.sockets[0]
        # BEGIN + 1 CHUNK + END = 3 packets, no retries expected.
        self.assertEqual(3, sock.attempt_count)

    def test_upload_retries_on_transient_oserror_then_succeeds(self):
        factory = make_failing_socket_factory([OSError("send buf full"), None])
        transport = MasterUdpUploadTransport(
            port=43690,
            chunk_size=1024,
            inter_packet_delay=0.0,
            max_retries=2,
            retry_base_delay=0.0,
            socket_factory=factory,
        )
        transport.upload(_make_compiled(blob=b"abc"))

        sock = factory.sockets[0]
        # 1 failed BEGIN + 1 retried BEGIN + 1 CHUNK + 1 END = 4.
        self.assertEqual(4, sock.attempt_count)

    def test_upload_raises_UploadFailedError_after_exhausting_retries(self):
        failures = [OSError("unreachable")] * 10
        factory = make_failing_socket_factory(failures)
        transport = MasterUdpUploadTransport(
            port=43690,
            chunk_size=1024,
            inter_packet_delay=0.0,
            max_retries=2,
            retry_base_delay=0.0,
            socket_factory=factory,
        )

        with self.assertRaises(UploadFailedError) as ctx:
            transport.upload(_make_compiled(host="10.0.0.1", blob=b"abc"))

        exc = ctx.exception
        self.assertEqual("10.0.0.1", exc.host)
        self.assertEqual(3, exc.attempts)
        self.assertIsInstance(exc.original, OSError)

    def test_start_show_uses_same_retry_path(self):
        factory = make_failing_socket_factory([OSError("transient"), None])
        transport = MasterUdpUploadTransport(
            port=43690,
            inter_packet_delay=0.0,
            max_retries=1,
            retry_base_delay=0.0,
            socket_factory=factory,
        )

        transport.start_show(["10.0.0.1"])

        sock = factory.sockets[0]
        self.assertEqual(2, sock.attempt_count)

    def test_start_show_raises_after_exhaustion(self):
        factory = make_failing_socket_factory(
            [OSError("down"), OSError("down"), OSError("down")]
        )
        transport = MasterUdpUploadTransport(
            port=43690,
            inter_packet_delay=0.0,
            max_retries=0,
            retry_base_delay=0.0,
            socket_factory=factory,
        )

        with self.assertRaises(UploadFailedError) as ctx:
            transport.start_show(["10.0.0.1"])

        self.assertEqual(1, ctx.exception.attempts)

    def test_uploadfailederror_carries_original_exception(self):
        original = ConnectionRefusedError("refused")
        factory = make_failing_socket_factory([original])
        transport = MasterUdpUploadTransport(
            port=43690,
            inter_packet_delay=0.0,
            max_retries=0,
            retry_base_delay=0.0,
            socket_factory=factory,
        )

        with self.assertRaises(UploadFailedError) as ctx:
            transport.start_show(["10.0.0.1"])

        exc = ctx.exception
        self.assertIsInstance(exc.original, ConnectionRefusedError)
        self.assertIn("1 attempt", str(exc))


if __name__ == "__main__":
    unittest.main()
