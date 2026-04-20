"""Pure UDP reachability probe. Returns a PingStatus enum without
touching Qt. Consumed by MasterPingWorker on the Qt side; unit-tested
by monkey-patching socket.socket."""
from __future__ import annotations

import socket
from enum import Enum


class PingStatus(str, Enum):
    """str-subclass so values serialize clean in logs and compare with
    "==" against strings in tests."""
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"


def ping_host(
    host: str,
    port: int,
    timeout: float = 1.0,
) -> PingStatus:
    """Open a UDP socket, connect to (host, port), send a zero-length
    datagram, close. Returns PingStatus.ONLINE on success,
    PingStatus.OFFLINE on OSError. Does NOT wait for any response.

    Empty host -> OFFLINE. Invalid port -> OFFLINE. Timeout applies
    to connect/send steps only."""
    if not host or not isinstance(host, str):
        return PingStatus.OFFLINE
    try:
        port_int = int(port)
    except (TypeError, ValueError):
        return PingStatus.OFFLINE
    if port_int <= 0 or port_int > 65535:
        return PingStatus.OFFLINE
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(max(0.01, float(timeout)))
        sock.connect((host, port_int))
        sock.send(b"")
        return PingStatus.ONLINE
    except OSError:
        return PingStatus.OFFLINE
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
