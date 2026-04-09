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

    def load_audio(self):
        return [0.1], 48000, "track.wav"

    def load_boxes(self):
        return {"m1": {"name": "Master 1"}}

    def save_audio(self, audio, sample_rate):
        self.saved_audio = audio
        self.saved_sr = sample_rate

    def save_boxes(self, masters):
        self.saved_masters = masters


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


if __name__ == "__main__":
    unittest.main()
