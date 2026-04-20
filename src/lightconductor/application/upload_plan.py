"""Pure planning for UDP upload. Given a compiled show keyed by host,
computes per-host and per-slave packet / byte counts, plus an estimated
transfer duration. Consumed by the pre-upload confirmation dialog. No
Qt, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from lightconductor.application.compiled_show import (
    CompiledSlaveShow,
)


@dataclass(slots=True, frozen=True)
class SlavePlan:
    slave_id: int
    blob_size: int
    chunk_count: int
    packet_count: int  # begin + chunks + end = 2 + chunk_count


@dataclass(slots=True, frozen=True)
class HostPlan:
    host: str
    slaves: List[SlavePlan] = field(default_factory=list)

    @property
    def total_packets(self) -> int:
        return sum(s.packet_count for s in self.slaves)

    @property
    def total_bytes(self) -> int:
        return sum(s.blob_size for s in self.slaves)


@dataclass(slots=True, frozen=True)
class UploadPlan:
    hosts: List[HostPlan] = field(default_factory=list)
    estimated_seconds: float = 0.0

    @property
    def total_hosts(self) -> int:
        return len(self.hosts)

    @property
    def total_slaves(self) -> int:
        return sum(len(h.slaves) for h in self.hosts)

    @property
    def total_packets(self) -> int:
        return sum(h.total_packets for h in self.hosts)

    @property
    def total_bytes(self) -> int:
        return sum(h.total_bytes for h in self.hosts)


def _ceil_div(a: int, b: int) -> int:
    if b <= 0:
        return 0
    return -(-a // b)


def build_upload_plan(
    compiled_by_host: Dict[str, List[CompiledSlaveShow]],
    chunk_size: int,
    inter_packet_delay: float,
) -> UploadPlan:
    """Compute the upload plan from compile output.

    - chunk_count per slave = ceil(blob_size / chunk_size).
      Empty blob -> 0 chunks.
    - packet_count per slave = 2 + chunk_count (BEGIN + chunks + END).
    - estimated_seconds = total_packets * inter_packet_delay. Sends are
      essentially fire-and-forget UDP; the delay is the dominant
      latency. Network jitter is NOT modeled - this is a rough
      pre-upload estimate.
    """
    if chunk_size <= 0:
        chunk_size = 1
    delay = max(0.0, float(inter_packet_delay or 0.0))
    hosts: List[HostPlan] = []
    for host in sorted(compiled_by_host.keys()):
        shows = compiled_by_host.get(host, [])
        slave_plans: List[SlavePlan] = []
        for show in shows:
            blob_size = len(show.blob or b"")
            chunk_count = _ceil_div(blob_size, chunk_size)
            packet_count = 2 + chunk_count
            slave_plans.append(
                SlavePlan(
                    slave_id=show.slave_id,
                    blob_size=blob_size,
                    chunk_count=chunk_count,
                    packet_count=packet_count,
                )
            )
        hosts.append(HostPlan(host=host, slaves=slave_plans))
    total_packets = sum(h.total_packets for h in hosts)
    estimated_seconds = total_packets * delay
    return UploadPlan(
        hosts=hosts,
        estimated_seconds=estimated_seconds,
    )
