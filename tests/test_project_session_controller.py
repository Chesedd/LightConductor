import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.domain.models import Master
from lightconductor.presentation import ProjectSessionController


class FakeStorage:
    def __init__(self, domain_masters=None):
        self.saved_audio = None
        self.saved_sr = None
        self.saved_masters = None
        self.calls = []
        self._domain_masters = domain_masters or {}

    def load_audio(self):
        return [0.1], 48000, "track.wav"

    def save_audio(self, audio, sample_rate):
        self.saved_audio = audio
        self.saved_sr = sample_rate
        self.calls.append("save_audio")

    def load_domain_masters(self):
        return self._domain_masters

    def save_domain_masters(self, masters):
        self.saved_masters = masters
        self.calls.append("save_domain_masters")


class ProjectSessionControllerTests(unittest.TestCase):
    def test_load_session(self):
        masters = {"m1": Master(id="m1", name="Master 1", ip="1.2.3.4")}
        controller = ProjectSessionController(FakeStorage(domain_masters=masters))
        snapshot = controller.load_session()
        self.assertEqual([0.1], snapshot.audio)
        self.assertEqual(48000, snapshot.sample_rate)
        self.assertEqual("track.wav", snapshot.audio_path)
        self.assertIs(masters, snapshot.masters)

    def test_save_session(self):
        storage = FakeStorage()
        controller = ProjectSessionController(storage)
        masters = {"m1": Master(id="m1", name="M", ip="1.2.3.4")}
        controller.save_session([3, 4], 22050, masters)
        self.assertEqual([3, 4], storage.saved_audio)
        self.assertEqual(22050, storage.saved_sr)
        self.assertIs(masters, storage.saved_masters)
        self.assertEqual(
            ["save_audio", "save_domain_masters"], storage.calls,
        )


if __name__ == "__main__":
    unittest.main()
