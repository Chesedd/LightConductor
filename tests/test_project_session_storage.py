import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.domain.models import Master, Slave, Tag, TagType
from lightconductor.infrastructure.project_file_backup import backup_path
from lightconductor.infrastructure.project_schema import CURRENT_SCHEMA_VERSION
from lightconductor.infrastructure.project_session_storage import (
    ProjectSessionStorage,
)

try:
    import librosa  # noqa: F401
    import numpy as np
    import soundfile  # noqa: F401

    HAVE_AUDIO = True
except ImportError:
    HAVE_AUDIO = False


def _make_master(master_id="m1", name="M1", ip="1.2.3.4", slaves=None):
    return Master(id=master_id, name=name, ip=ip, slaves=slaves or {})


def _make_full_master():
    tag = Tag(time_seconds=1.25, action=True, colors=[[10, 20, 30]])
    tag_type = TagType(
        name="red",
        pin="3",
        rows=1,
        columns=2,
        color=[255, 0, 0],
        topology=[0, 1, 2, 3],
        tags=[tag],
    )
    slave = Slave(
        id="s1",
        name="Slave 1",
        pin="5",
        led_count=30,
        tag_types={"red": tag_type},
    )
    return Master(id="m1", name="M1", ip="1.2.3.4", slaves={"s1": slave})


class MastersStorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.storage = ProjectSessionStorage(projects_root=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_masters_returns_empty_dict_if_file_missing(self):
        self.assertEqual(self.storage.load_masters("proj_A"), {})

    def test_save_masters_creates_project_dir_and_file(self):
        masters = {"m1": _make_master()}
        self.storage.save_masters("proj_A", masters)
        self.assertTrue((self.root / "proj_A" / "data.json").exists())

    def test_save_masters_writes_current_envelope(self):
        self.storage.save_masters("proj_A", {"m1": _make_master()})
        raw = json.loads(
            (self.root / "proj_A" / "data.json").read_text(encoding="utf-8")
        )
        self.assertEqual(raw["schema_version"], CURRENT_SCHEMA_VERSION)
        self.assertIn("masters", raw)
        self.assertIn("m1", raw["masters"])

    def test_save_then_load_roundtrip_single_master(self):
        masters_in = {"m1": _make_master()}
        self.storage.save_masters("proj", masters_in)
        masters_out = self.storage.load_masters("proj")
        self.assertEqual(masters_out, masters_in)

    def test_save_then_load_roundtrip_full_tree(self):
        masters_in = {
            "m1": _make_full_master(),
            "m2": _make_master(master_id="m2", name="M2", ip="5.6.7.8"),
        }
        self.storage.save_masters("proj", masters_in)
        masters_out = self.storage.load_masters("proj")
        self.assertEqual(masters_out, masters_in)

    def test_load_masters_migrates_legacy_v0_file(self):
        legacy_boxes = {
            "m1": {
                "name": "M1",
                "id": "m1",
                "ip": "1.2.3.4",
                "slaves": {},
            }
        }
        project_dir = self.root / "proj"
        project_dir.mkdir(parents=True)
        (project_dir / "data.json").write_text(
            json.dumps(legacy_boxes), encoding="utf-8"
        )
        masters_out = self.storage.load_masters("proj")
        self.assertEqual(
            masters_out,
            {"m1": Master(id="m1", name="M1", ip="1.2.3.4", slaves={})},
        )

    def test_save_masters_rotates_backups(self):
        self.storage.save_masters("proj", {"m1": _make_master(name="V1")})
        first_bytes = (self.root / "proj" / "data.json").read_bytes()
        self.storage.save_masters("proj", {"m1": _make_master(name="V2")})
        bak1 = backup_path(self.root / "proj" / "data.json", 1)
        self.assertTrue(bak1.exists())
        self.assertEqual(bak1.read_bytes(), first_bytes)


@unittest.skipUnless(HAVE_AUDIO, "audio libs not installed")
class AudioStorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.storage = ProjectSessionStorage(projects_root=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_audio_with_none_is_noop(self):
        self.storage.save_audio("proj", None, 44100)
        self.assertFalse((self.root / "proj" / "audio.wav").exists())

    def test_load_audio_returns_none_tuple_if_missing(self):
        audio, sr, path = self.storage.load_audio("proj")
        self.assertIsNone(audio)
        self.assertIsNone(sr)
        self.assertTrue(path.endswith("audio.wav"))

    def test_save_then_load_audio_roundtrip(self):
        signal = np.sin(np.linspace(0, 1, 1000)).astype("float32")
        self.storage.save_audio("proj", signal, 44100)
        audio, sr, path = self.storage.load_audio("proj")
        self.assertEqual(sr, 44100)
        self.assertIsNotNone(audio)
        self.assertEqual(len(audio), len(signal))
        self.assertTrue(path.endswith("audio.wav"))


class CrossCuttingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.storage = ProjectSessionStorage(projects_root=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_audio_and_data_independent(self):
        self.storage.save_masters("proj", {"m1": _make_master()})
        audio, sr, _ = self.storage.load_audio("proj")
        self.assertIsNone(audio)
        self.assertIsNone(sr)

        # Fresh project: saving audio alone (None is a no-op so we use an
        # empty bytes-based check — save_audio with None MUST NOT create
        # a wav, and load_masters MUST return {} for a project that has
        # only the audio file (or nothing) on disk).
        self.storage.save_audio("proj2", None, 44100)
        self.assertEqual(self.storage.load_masters("proj2"), {})


if __name__ == "__main__":
    unittest.main()
