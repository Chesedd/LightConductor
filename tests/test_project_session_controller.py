import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.presentation import ProjectSessionController


class FakeStorage:
    def __init__(self):
        self.saved_audio = None
        self.saved_sr = None
        self.saved_masters = None
        self.saved_domain_masters = None
        self.calls = []

    def load_audio(self):
        return [0.1], 48000, "track.wav"

    def load_boxes(self):
        return {"m1": {"name": "Master 1"}}

    def save_audio(self, audio, sample_rate):
        self.saved_audio = audio
        self.saved_sr = sample_rate
        self.calls.append("save_audio")

    def save_boxes(self, masters):
        self.saved_masters = masters
        self.calls.append("save_boxes")

    def load_domain_masters(self):
        return {}

    def save_domain_masters(self, masters):
        self.saved_domain_masters = masters
        self.calls.append("save_domain_masters")


class ProjectSessionControllerTests(unittest.TestCase):
    def test_load_session(self):
        controller = ProjectSessionController(FakeStorage())
        snapshot = controller.load_session()
        self.assertEqual([0.1], snapshot.audio)
        self.assertEqual(48000, snapshot.sample_rate)
        self.assertEqual("track.wav", snapshot.audio_path)
        self.assertEqual({"m1": {"name": "Master 1"}}, snapshot.boxes)

    def test_save_session(self):
        storage = FakeStorage()
        controller = ProjectSessionController(storage)
        controller.save_session([1, 2], 44100, {"m": {"id": 1}})
        self.assertEqual([1, 2], storage.saved_audio)
        self.assertEqual(44100, storage.saved_sr)
        self.assertEqual({"m": {"id": 1}}, storage.saved_masters)

    def test_save_session_domain_invokes_save_audio_then_save_domain_masters(self):
        from lightconductor.domain.models import Master

        storage = FakeStorage()
        controller = ProjectSessionController(storage)
        masters = {"m1": Master(id="m1", name="M", ip="1.2.3.4")}
        controller.save_session_domain([3, 4], 22050, masters)

        self.assertEqual([3, 4], storage.saved_audio)
        self.assertEqual(22050, storage.saved_sr)
        self.assertIs(masters, storage.saved_domain_masters)
        self.assertEqual(
            ["save_audio", "save_domain_masters"], storage.calls,
        )


if __name__ == "__main__":
    unittest.main()
