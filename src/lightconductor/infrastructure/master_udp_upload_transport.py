from __future__ import annotations

import socket
import struct
import time
from typing import Dict, Iterable, List

from lightconductor.application.compiled_show import CompiledSlaveShow

APP_MAGIC = b"LCM1"

CMD_UPLOAD_BEGIN = 0x10
CMD_UPLOAD_CHUNK = 0x11
CMD_UPLOAD_END = 0x12
CMD_START_SHOW = 0x20

BEGIN_STRUCT = struct.Struct("<4sBBII")   # magic, cmd, slave_id, total_size, crc32
CHUNK_HEAD_STRUCT = struct.Struct("<4sBBIH")  # magic, cmd, slave_id, offset, chunk_len
END_STRUCT = struct.Struct("<4sBB")
START_STRUCT = struct.Struct("<4sB")


class MasterUdpUploadTransport:
    def __init__(self, port: int = 43690, chunk_size: int = 768, inter_packet_delay: float = 0.002):
        self.port = port
        self.chunk_size = chunk_size
        self.inter_packet_delay = inter_packet_delay

    def upload(self, compiled_by_host: Dict[str, List[CompiledSlaveShow]]) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            for host, shows in compiled_by_host.items():
                for show in shows:
                    sock.sendto(
                        BEGIN_STRUCT.pack(APP_MAGIC, CMD_UPLOAD_BEGIN, show.slave_id, len(show.blob), show.crc32),
                        (host, self.port),
                    )
                    time.sleep(self.inter_packet_delay)

                    offset = 0
                    while offset < len(show.blob):
                        chunk = show.blob[offset : offset + self.chunk_size]
                        packet = CHUNK_HEAD_STRUCT.pack(
                            APP_MAGIC,
                            CMD_UPLOAD_CHUNK,
                            show.slave_id,
                            offset,
                            len(chunk),
                        ) + chunk
                        sock.sendto(packet, (host, self.port))
                        offset += len(chunk)
                        time.sleep(self.inter_packet_delay)

                    sock.sendto(END_STRUCT.pack(APP_MAGIC, CMD_UPLOAD_END, show.slave_id), (host, self.port))
                    time.sleep(self.inter_packet_delay)
        finally:
            sock.close()

    def start_show(self, hosts: Iterable[str]) -> None:
        unique_hosts = sorted({host for host in hosts if host})
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            payload = START_STRUCT.pack(APP_MAGIC, CMD_START_SHOW)
            for host in unique_hosts:
                sock.sendto(payload, (host, self.port))
                time.sleep(self.inter_packet_delay)
        finally:
            sock.close()