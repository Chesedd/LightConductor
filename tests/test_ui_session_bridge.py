"""Coverage for UiSessionBridge (PR 1.2.2b).

The bridge adapts ProjectSessionStorage (domain-based, uses
`Dict[str, Master]`) to the no-argument method shape the UI layer
expects (dict-based boxes). Every test uses its own temp directory
for isolation.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.infrastructure.json_mapper import pack_master
from lightconductor.infrastructure.project_session_storage import (
    ProjectSessionStorage,
)
from lightconductor.infrastructure.ui_masters_mapper import (
    UiMastersMapper,
)
from lightconductor.infrastructure.ui_session_bridge import (
    UiSessionBridge,
)

try:
    import librosa  # noqa: F401
    import numpy  # noqa: F401
    import soundfile  # noqa: F401
    HAVE_AUDIO = True
except ImportError:
    HAVE_AUDIO = False


def _make_fake_master(title="Master A", master_ip="10.0.0.5", slaves=None):
    m = SimpleNamespace()
    m.title = title
    m.masterIp = master_ip
    m.slaves = slaves or {}
    return m


def _make_fake_slave(title="Slave A", slave_pin="7", led_count=60, types=None):
    manager = SimpleNamespace(types=types or {})
    wave = SimpleNamespace(manager=manager)
    s = SimpleNamespace()
    s.title = title
    s.slavePin = slave_pin
    s.ledCount = led_count
    s.wave = wave
    return s


def _make_fake_type(pin="3", row=2, table=2, color=[255, 255, 255],
                    topology=(0, 1, 2, 3), tags=None):
    return SimpleNamespace(
        pin=pin, row=row, table=table, color=color,
        topology=list(topology), tags=tags or [],
    )


def _make_fake_tag(time=0.1, action=True, colors=None):
    return SimpleNamespace(
        time=time, action=action,
        colors=colors or [[255, 0, 0]],
    )


def _make_bridge(projects_root: Path, project_name: str = "proj1") -> UiSessionBridge:
    return UiSessionBridge(
        domain_storage=ProjectSessionStorage(projects_root=projects_root),
        project_name=project_name,
        ui_mapper=UiMastersMapper(),
    )


class UiSessionBridgeTests(unittest.TestCase):

    def test_load_boxes_returns_empty_if_no_data_file(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = _make_bridge(Path(td))
            self.assertEqual(bridge.load_boxes(), {})

    def test_save_boxes_then_load_boxes_roundtrip_via_pack_master(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = _make_bridge(Path(td))
            tag = _make_fake_tag(time=0.1, action=True, colors=[[1, 2, 3]])
            t = _make_fake_type(
                pin="3", row=1, table=4, color=[255, 0, 0],
                topology=[0, 1, 2, 3], tags=[tag],
            )
            slave = _make_fake_slave(
                title="S", slave_pin="7", led_count=60,
                types={"front": t},
            )
            master = _make_fake_master(
                title="M", master_ip="10.0.0.5",
                slaves={"s1": slave},
            )
            ui_masters = {"m1": master}

            bridge.save_boxes(ui_masters)
            loaded = bridge.load_boxes()

            # load_boxes runs pack_master on the stored domain objects,
            # so the returned dict must match a re-pack of the mapped
            # domain tree.
            mapper = UiMastersMapper()
            domain = mapper.map_masters(ui_masters)
            expected = {
                mid: pack_master(m) for mid, m in domain.items()
            }
            self.assertEqual(loaded, expected)

    def test_save_boxes_creates_data_json_with_schema_version(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = _make_bridge(Path(td), project_name="p2")
            bridge.save_boxes({})
            data_path = Path(td) / "p2" / "data.json"
            self.assertTrue(data_path.exists())
            with data_path.open("r", encoding="utf-8") as fh:
                envelope = json.load(fh)
            self.assertEqual(envelope.get("schema_version"), 1)
            self.assertEqual(envelope.get("masters"), {})

    def test_save_boxes_persists_custom_ip(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = _make_bridge(Path(td))
            master = _make_fake_master(
                title="M", master_ip="192.168.99.99", slaves={},
            )
            bridge.save_boxes({"m1": master})
            loaded = bridge.load_boxes()
            self.assertEqual(loaded["m1"]["ip"], "192.168.99.99")

    def test_save_boxes_handles_empty_masters(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = _make_bridge(Path(td), project_name="empty_p")
            bridge.save_boxes({})
            data_path = Path(td) / "empty_p" / "data.json"
            self.assertTrue(data_path.exists())
            with data_path.open("r", encoding="utf-8") as fh:
                envelope = json.load(fh)
            self.assertEqual(envelope, {"schema_version": 1, "masters": {}})

    def test_load_audio_delegates_with_project_name(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = _make_bridge(Path(td), project_name="p3")
            audio, sr, path = bridge.load_audio()
            self.assertIsNone(audio)
            self.assertIsNone(sr)
            expected_path = Path(td) / "p3" / "audio.wav"
            self.assertEqual(Path(path), expected_path)

    @unittest.skipUnless(HAVE_AUDIO, "librosa/soundfile/numpy not available")
    def test_save_audio_delegates_with_project_name(self):
        import numpy as np

        with tempfile.TemporaryDirectory() as td:
            bridge = _make_bridge(Path(td), project_name="p4")
            # 1 second of silence at 44.1 kHz
            buf = np.zeros(44100, dtype=np.float32)
            bridge.save_audio(buf, 44100)
            audio_path = Path(td) / "p4" / "audio.wav"
            self.assertTrue(audio_path.exists())

            # Round-trip via load_audio too.
            audio, sr, path = bridge.load_audio()
            self.assertIsNotNone(audio)
            self.assertEqual(sr, 44100)
            self.assertEqual(Path(path), audio_path)

    def test_save_audio_none_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = _make_bridge(Path(td), project_name="p5")
            bridge.save_audio(None, None)
            audio_path = Path(td) / "p5" / "audio.wav"
            self.assertFalse(audio_path.exists())

    def test_load_domain_masters_returns_domain_instances(self):
        from unittest.mock import MagicMock

        from lightconductor.domain.models import Master, Slave

        storage = MagicMock()
        domain_dict = {
            "m1": Master(
                id="m1", name="M", ip="1.2.3.4",
                slaves={"s1": Slave(id="s1", name="S", pin="0")},
            ),
        }
        storage.load_masters.return_value = domain_dict

        bridge = UiSessionBridge(
            domain_storage=storage,
            project_name="proj",
            ui_mapper=UiMastersMapper(),
        )
        result = bridge.load_domain_masters()

        self.assertIs(result, domain_dict)
        storage.load_masters.assert_called_once_with("proj")

    def test_save_domain_masters_delegates_to_storage(self):
        from unittest.mock import MagicMock

        from lightconductor.domain.models import Master

        storage = MagicMock()
        bridge = UiSessionBridge(
            domain_storage=storage,
            project_name="proj",
            ui_mapper=UiMastersMapper(),
        )
        masters = {"m1": Master(id="m1", name="M", ip="1.2.3.4")}
        bridge.save_domain_masters(masters)

        storage.save_masters.assert_called_once_with("proj", masters)

    def test_bridge_separate_project_names_are_isolated(self):
        with tempfile.TemporaryDirectory() as td:
            storage = ProjectSessionStorage(projects_root=Path(td))
            mapper = UiMastersMapper()
            bridge_a = UiSessionBridge(
                domain_storage=storage,
                project_name="alpha",
                ui_mapper=mapper,
            )
            bridge_b = UiSessionBridge(
                domain_storage=storage,
                project_name="beta",
                ui_mapper=mapper,
            )
            master_a = _make_fake_master(
                title="A", master_ip="1.1.1.1", slaves={},
            )
            bridge_a.save_boxes({"m1": master_a})

            self.assertEqual(bridge_b.load_boxes(), {})
            loaded_a = bridge_a.load_boxes()
            self.assertIn("m1", loaded_a)
            self.assertEqual(loaded_a["m1"]["ip"], "1.1.1.1")


if __name__ == "__main__":
    unittest.main()
