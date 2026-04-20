from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(slots=True)
class UdpTransportConfig:
    host: str
    port: int = 12345


class UdpShowTransport:
    def __init__(self, config: UdpTransportConfig):
        self.config = config

    def send_payload(
        self,
        pins: Dict[str, Dict[str, int]],
        payload: Dict[str, Dict[int, Dict[str, Any]]],
    ) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        try:
            sock.sendto("pins".encode("utf-8"), (self.config.host, self.config.port))
            sock.sendto(
                json.dumps(pins).encode("utf-8"), (self.config.host, self.config.port)
            )
            sock.sendto(
                "partiture".encode("utf-8"), (self.config.host, self.config.port)
            )

            for slave_pin, slave_payload in payload.items():
                sock.sendto(
                    slave_pin.encode("utf-8"), (self.config.host, self.config.port)
                )
                sock.sendto(
                    json.dumps(slave_payload).encode("utf-8"),
                    (self.config.host, self.config.port),
                )

            sock.sendto("end".encode("utf-8"), (self.config.host, self.config.port))
        finally:
            sock.close()

    def send_start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.sendto("start".encode("utf-8"), (self.config.host, self.config.port))
        finally:
            sock.close()
