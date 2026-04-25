"""Coverage for UiSessionBridge.

The bridge adapts ProjectSessionStorage (domain-based, uses
`Dict[str, Master]`) to the no-argument method shape the UI layer
expects. Every test uses its own temp directory for isolation.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.domain.models import Master, Slave, Tag, TagType
from lightconductor.infrastructure.project_schema import CURRENT_SCHEMA_VERSION
from lightconductor.infrastructure.project_session_storage import (
    ProjectSessionStorage,
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


def _make_bridge(projects_root: Path, project_name: str = "proj1") -> UiSessionBridge:
    return UiSessionBridge(
        domain_storage=ProjectSessionStorage(projects_root=projects_root),
        project_name=project_name,
    )


def _sample_master(master_id: str = "m1", ip: str = "10.0.0.5") -> Master:
    tag_type = TagType(
        name="front",
        pin="3",
        rows=1,
        columns=4,
        color=[255, 0, 0],
        topology=[0, 1, 2, 3],
        tags=[Tag(time_seconds=0.1, action=True, colors=[[1, 2, 3]])],
    )
    slave = Slave(
        id="s1",
        name="S",
        pin="7",
        led_count=60,
        tag_types={"front": tag_type},
    )
    return Master(
        id=master_id,
        name="M",
        ip=ip,
        slaves={"s1": slave},
    )


class UiSessionBridgeTests(unittest.TestCase):
    def test_load_domain_masters_returns_empty_if_no_data_file(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = _make_bridge(Path(td))
            self.assertEqual(bridge.load_domain_masters(), {})

    def test_save_domain_masters_then_load_domain_masters_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = _make_bridge(Path(td))
            master = _sample_master()
            bridge.save_domain_masters({"m1": master})
            loaded = bridge.load_domain_masters()

            self.assertIn("m1", loaded)
            self.assertEqual(loaded["m1"].name, master.name)
            self.assertEqual(loaded["m1"].ip, master.ip)
            self.assertIn("s1", loaded["m1"].slaves)
            self.assertEqual(loaded["m1"].slaves["s1"].pin, "7")
            self.assertIn("front", loaded["m1"].slaves["s1"].tag_types)

    def test_save_domain_masters_creates_data_json_with_schema_version(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = _make_bridge(Path(td), project_name="p2")
            bridge.save_domain_masters({})
            data_path = Path(td) / "p2" / "data.json"
            self.assertTrue(data_path.exists())
            with data_path.open("r", encoding="utf-8") as fh:
                envelope = json.load(fh)
            self.assertEqual(envelope.get("schema_version"), CURRENT_SCHEMA_VERSION)
            self.assertEqual(envelope.get("masters"), {})

    def test_save_domain_masters_persists_custom_ip(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = _make_bridge(Path(td))
            master = Master(id="m1", name="M", ip="192.168.99.99")
            bridge.save_domain_masters({"m1": master})
            loaded = bridge.load_domain_masters()
            self.assertEqual(loaded["m1"].ip, "192.168.99.99")

    def test_save_domain_masters_handles_empty_masters(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = _make_bridge(Path(td), project_name="empty_p")
            bridge.save_domain_masters({})
            data_path = Path(td) / "empty_p" / "data.json"
            self.assertTrue(data_path.exists())
            with data_path.open("r", encoding="utf-8") as fh:
                envelope = json.load(fh)
            self.assertEqual(
                envelope, {"schema_version": CURRENT_SCHEMA_VERSION, "masters": {}}
            )

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
            buf = np.zeros(44100, dtype=np.float32)
            bridge.save_audio(buf, 44100)
            audio_path = Path(td) / "p4" / "audio.wav"
            self.assertTrue(audio_path.exists())

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

    def test_load_domain_masters_delegates_to_storage(self):
        storage = MagicMock()
        domain_dict = {
            "m1": Master(
                id="m1",
                name="M",
                ip="1.2.3.4",
                slaves={"s1": Slave(id="s1", name="S", pin="0")},
            ),
        }
        storage.load_masters.return_value = domain_dict

        bridge = UiSessionBridge(
            domain_storage=storage,
            project_name="proj",
        )
        result = bridge.load_domain_masters()

        self.assertIs(result, domain_dict)
        storage.load_masters.assert_called_once_with("proj")

    def test_save_domain_masters_delegates_to_storage(self):
        storage = MagicMock()
        bridge = UiSessionBridge(
            domain_storage=storage,
            project_name="proj",
        )
        masters = {"m1": Master(id="m1", name="M", ip="1.2.3.4")}
        bridge.save_domain_masters(masters)

        storage.save_masters.assert_called_once_with("proj", masters)

    def test_bridge_separate_project_names_are_isolated(self):
        with tempfile.TemporaryDirectory() as td:
            storage = ProjectSessionStorage(projects_root=Path(td))
            bridge_a = UiSessionBridge(
                domain_storage=storage,
                project_name="alpha",
            )
            bridge_b = UiSessionBridge(
                domain_storage=storage,
                project_name="beta",
            )
            master_a = Master(id="m1", name="A", ip="1.1.1.1")
            bridge_a.save_domain_masters({"m1": master_a})

            self.assertEqual(bridge_b.load_domain_masters(), {})
            loaded_a = bridge_a.load_domain_masters()
            self.assertIn("m1", loaded_a)
            self.assertEqual(loaded_a["m1"].ip, "1.1.1.1")


if __name__ == "__main__":
    unittest.main()
