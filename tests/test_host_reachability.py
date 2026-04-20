import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.host_reachability import (
    PingStatus,
    ping_host,
)


class FakePingSocket:
    def __init__(
        self,
        connect_error=None,
        send_error=None,
        close_error=None,
    ):
        self._connect_error = connect_error
        self._send_error = send_error
        self._close_error = close_error
        self.timeout_set = None
        self.connect_called_with = None
        self.send_called_with = None
        self.close_called = False

    def settimeout(self, t):
        self.timeout_set = t

    def connect(self, addr):
        self.connect_called_with = addr
        if self._connect_error is not None:
            raise self._connect_error

    def send(self, data):
        self.send_called_with = data
        if self._send_error is not None:
            raise self._send_error
        return len(data)

    def close(self):
        self.close_called = True
        if self._close_error is not None:
            raise self._close_error


class _SocketPatcher:
    """Context manager that replaces socket.socket inside
    host_reachability module with a factory that returns a given
    FakePingSocket."""

    def __init__(self, fake):
        self.fake = fake
        self._orig = None

    def __enter__(self):
        from lightconductor.application import host_reachability

        self._orig = host_reachability.socket.socket
        host_reachability.socket.socket = lambda *a, **kw: self.fake
        return self

    def __exit__(self, *a):
        from lightconductor.application import host_reachability

        host_reachability.socket.socket = self._orig


class PingStatusValuesTests(unittest.TestCase):
    def test_ping_status_values(self):
        self.assertEqual(PingStatus.UNKNOWN.value, "unknown")
        self.assertEqual(PingStatus.ONLINE.value, "online")
        self.assertEqual(PingStatus.OFFLINE.value, "offline")
        # str-subclass: equality against plain string works.
        self.assertTrue(PingStatus.ONLINE == "online")


class PingInputValidationTests(unittest.TestCase):
    def test_ping_empty_host_returns_offline(self):
        self.assertEqual(
            ping_host("", 43690, 1.0),
            PingStatus.OFFLINE,
        )
        self.assertEqual(
            ping_host(None, 43690, 1.0),
            PingStatus.OFFLINE,
        )

    def test_ping_invalid_port_returns_offline(self):
        self.assertEqual(
            ping_host("10.0.0.1", 0, 1.0),
            PingStatus.OFFLINE,
        )
        self.assertEqual(
            ping_host("10.0.0.1", -1, 1.0),
            PingStatus.OFFLINE,
        )
        self.assertEqual(
            ping_host("10.0.0.1", 70000, 1.0),
            PingStatus.OFFLINE,
        )
        self.assertEqual(
            ping_host("10.0.0.1", "not-a-number", 1.0),
            PingStatus.OFFLINE,
        )


class PingSocketBehaviorTests(unittest.TestCase):
    def test_ping_successful_connect_and_send_returns_online(self):
        fake = FakePingSocket()
        with _SocketPatcher(fake):
            result = ping_host("10.0.0.1", 43690, 1.0)
        self.assertEqual(result, PingStatus.ONLINE)
        self.assertEqual(
            fake.connect_called_with,
            ("10.0.0.1", 43690),
        )
        self.assertEqual(fake.send_called_with, b"")
        self.assertTrue(fake.close_called)

    def test_ping_connect_raises_oserror_returns_offline(self):
        fake = FakePingSocket(
            connect_error=OSError("no route to host"),
        )
        with _SocketPatcher(fake):
            result = ping_host("10.0.0.1", 43690, 1.0)
        self.assertEqual(result, PingStatus.OFFLINE)
        self.assertTrue(fake.close_called)

    def test_ping_send_raises_oserror_returns_offline(self):
        fake = FakePingSocket(send_error=OSError("send failed"))
        with _SocketPatcher(fake):
            result = ping_host("10.0.0.1", 43690, 1.0)
        self.assertEqual(result, PingStatus.OFFLINE)
        self.assertTrue(fake.close_called)

    def test_ping_close_oserror_is_swallowed(self):
        fake = FakePingSocket(close_error=OSError("close failed"))
        with _SocketPatcher(fake):
            result = ping_host("10.0.0.1", 43690, 1.0)
        self.assertEqual(result, PingStatus.ONLINE)
        self.assertTrue(fake.close_called)

    def test_ping_timeout_minimum_is_clamped(self):
        fake = FakePingSocket()
        with _SocketPatcher(fake):
            result = ping_host("10.0.0.1", 43690, 0.0)
        self.assertEqual(result, PingStatus.ONLINE)
        self.assertIsNotNone(fake.timeout_set)
        self.assertGreaterEqual(fake.timeout_set, 0.01)

    def test_ping_sends_empty_payload(self):
        fake = FakePingSocket()
        with _SocketPatcher(fake):
            ping_host("10.0.0.1", 43690, 1.0)
        self.assertEqual(fake.send_called_with, b"")

    def test_ping_hostname_and_port_passed_to_connect(self):
        fake = FakePingSocket()
        with _SocketPatcher(fake):
            ping_host("example.invalid", 12345, 1.0)
        self.assertEqual(
            fake.connect_called_with,
            ("example.invalid", 12345),
        )


if __name__ == "__main__":
    unittest.main()
