import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.compiled_show import CompiledSlaveShow
from lightconductor.application.upload_plan import (
    HostPlan,
    SlavePlan,
    UploadPlan,
    build_upload_plan,
)


def _fake_compiled(host: str, slave_id: int, blob: bytes) -> CompiledSlaveShow:
    return CompiledSlaveShow(
        master_ip=host,
        slave_id=slave_id,
        total_led_count=16,
        blob=blob,
    )


class UploadPlanTests(unittest.TestCase):
    def test_empty_input_produces_empty_plan(self):
        plan = build_upload_plan(
            compiled_by_host={},
            chunk_size=100,
            inter_packet_delay=0.0,
        )
        self.assertIsInstance(plan, UploadPlan)
        self.assertEqual(plan.total_hosts, 0)
        self.assertEqual(plan.total_slaves, 0)
        self.assertEqual(plan.total_packets, 0)
        self.assertEqual(plan.total_bytes, 0)
        self.assertEqual(plan.estimated_seconds, 0.0)

    def test_single_host_single_slave_small_blob(self):
        compiled = {
            "10.0.0.1": [_fake_compiled("10.0.0.1", 1, b"x" * 50)],
        }
        plan = build_upload_plan(
            compiled_by_host=compiled,
            chunk_size=100,
            inter_packet_delay=0.0,
        )
        self.assertEqual(plan.total_hosts, 1)
        self.assertEqual(plan.total_slaves, 1)
        self.assertEqual(plan.total_bytes, 50)
        host = plan.hosts[0]
        self.assertIsInstance(host, HostPlan)
        self.assertEqual(host.host, "10.0.0.1")
        self.assertEqual(len(host.slaves), 1)
        slave = host.slaves[0]
        self.assertIsInstance(slave, SlavePlan)
        self.assertEqual(slave.slave_id, 1)
        self.assertEqual(slave.blob_size, 50)
        self.assertEqual(slave.chunk_count, 1)
        self.assertEqual(slave.packet_count, 3)
        self.assertEqual(plan.total_packets, 3)

    def test_exact_multiple_of_chunk_size(self):
        compiled = {
            "10.0.0.1": [_fake_compiled("10.0.0.1", 2, b"x" * 200)],
        }
        plan = build_upload_plan(
            compiled_by_host=compiled,
            chunk_size=100,
            inter_packet_delay=0.0,
        )
        slave = plan.hosts[0].slaves[0]
        self.assertEqual(slave.chunk_count, 2)
        self.assertEqual(slave.packet_count, 4)

    def test_non_multiple_rounds_up(self):
        compiled = {
            "10.0.0.1": [_fake_compiled("10.0.0.1", 3, b"x" * 201)],
        }
        plan = build_upload_plan(
            compiled_by_host=compiled,
            chunk_size=100,
            inter_packet_delay=0.0,
        )
        slave = plan.hosts[0].slaves[0]
        self.assertEqual(slave.chunk_count, 3)
        self.assertEqual(slave.packet_count, 5)

    def test_empty_blob_zero_chunks_but_two_packets(self):
        compiled = {
            "10.0.0.1": [_fake_compiled("10.0.0.1", 4, b"")],
        }
        plan = build_upload_plan(
            compiled_by_host=compiled,
            chunk_size=100,
            inter_packet_delay=0.0,
        )
        slave = plan.hosts[0].slaves[0]
        self.assertEqual(slave.blob_size, 0)
        self.assertEqual(slave.chunk_count, 0)
        self.assertEqual(slave.packet_count, 2)
        self.assertEqual(plan.total_bytes, 0)

    def test_multiple_hosts_sorted_alphabetically(self):
        compiled = {
            "10.0.0.2": [_fake_compiled("10.0.0.2", 5, b"x" * 10)],
            "10.0.0.1": [_fake_compiled("10.0.0.1", 6, b"x" * 10)],
        }
        plan = build_upload_plan(
            compiled_by_host=compiled,
            chunk_size=100,
            inter_packet_delay=0.0,
        )
        self.assertEqual(plan.hosts[0].host, "10.0.0.1")
        self.assertEqual(plan.hosts[1].host, "10.0.0.2")

    def test_multiple_slaves_per_host_aggregate(self):
        compiled = {
            "10.0.0.1": [
                _fake_compiled("10.0.0.1", 1, b"x" * 50),
                _fake_compiled("10.0.0.1", 2, b"x" * 100),
                _fake_compiled("10.0.0.1", 3, b"x" * 150),
            ],
        }
        plan = build_upload_plan(
            compiled_by_host=compiled,
            chunk_size=100,
            inter_packet_delay=0.0,
        )
        host = plan.hosts[0]
        self.assertEqual(len(host.slaves), 3)
        self.assertEqual(host.slaves[0].chunk_count, 1)
        self.assertEqual(host.slaves[1].chunk_count, 1)
        self.assertEqual(host.slaves[2].chunk_count, 2)
        self.assertEqual(host.total_packets, 10)
        self.assertEqual(host.total_bytes, 300)

    def test_estimated_seconds_scales_with_total_packets(self):
        compiled = {
            "10.0.0.1": [_fake_compiled("10.0.0.1", 1, b"x" * 100)],
        }
        plan = build_upload_plan(
            compiled_by_host=compiled,
            chunk_size=100,
            inter_packet_delay=0.01,
        )
        self.assertEqual(plan.total_packets, 3)
        self.assertAlmostEqual(plan.estimated_seconds, 0.03, places=6)

    def test_chunk_size_zero_defaults_to_one(self):
        compiled = {
            "10.0.0.1": [_fake_compiled("10.0.0.1", 1, b"x" * 10)],
        }
        plan = build_upload_plan(
            compiled_by_host=compiled,
            chunk_size=0,
            inter_packet_delay=0.0,
        )
        slave = plan.hosts[0].slaves[0]
        self.assertEqual(slave.chunk_count, 10)
        self.assertEqual(slave.packet_count, 12)

    def test_negative_inter_packet_delay_clamped_to_zero(self):
        compiled = {
            "10.0.0.1": [_fake_compiled("10.0.0.1", 1, b"x" * 500)],
        }
        plan = build_upload_plan(
            compiled_by_host=compiled,
            chunk_size=100,
            inter_packet_delay=-1.0,
        )
        self.assertGreater(plan.total_packets, 0)
        self.assertEqual(plan.estimated_seconds, 0.0)

    def test_build_upload_plan_redundancy_multiplies_chunks_and_seconds(self):
        # 2 hosts, 1 slave each, blob = 250 bytes @ chunk_size=100 -> 3 chunks.
        # Per slave (N=1): 2 + 3 = 5 packets. Total across 2 slaves = 10.
        # Per slave (N=2): 2 + 3*2 = 8 packets. Total = 16.
        # Difference = 6 = (chunk_count * (N-1)) * num_slaves = 3 * 1 * 2.
        compiled = {
            "10.0.0.1": [_fake_compiled("10.0.0.1", 1, b"x" * 250)],
            "10.0.0.2": [_fake_compiled("10.0.0.2", 2, b"x" * 250)],
        }
        plan_n1 = build_upload_plan(
            compiled_by_host=compiled,
            chunk_size=100,
            inter_packet_delay=0.01,
            chunk_redundancy=1,
        )
        plan_n2 = build_upload_plan(
            compiled_by_host=compiled,
            chunk_size=100,
            inter_packet_delay=0.01,
            chunk_redundancy=2,
        )
        self.assertEqual(plan_n1.total_packets, 10)
        self.assertEqual(plan_n2.total_packets, 16)
        # chunk_count remains the unique count (not multiplied).
        for host_plan in plan_n2.hosts:
            self.assertEqual(host_plan.slaves[0].chunk_count, 3)
            self.assertEqual(host_plan.slaves[0].packet_count, 8)
        # estimated_seconds scales with the new packet total.
        self.assertAlmostEqual(plan_n1.estimated_seconds, 0.10, places=6)
        self.assertAlmostEqual(plan_n2.estimated_seconds, 0.16, places=6)


if __name__ == "__main__":
    unittest.main()
