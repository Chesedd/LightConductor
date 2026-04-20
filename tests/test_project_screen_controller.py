import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.compiled_show import CompiledSlaveShow
from lightconductor.domain.models import Master
from lightconductor.presentation import ProjectScreenController


class FakeUseCase:
    def __init__(self):
        self.called_with = None

    def execute(self, masters):
        self.called_with = masters
        return {
            "10.0.0.1": [
                CompiledSlaveShow(
                    master_ip="10.0.0.1",
                    slave_id=1,
                    total_led_count=0,
                    blob=b"",
                )
            ]
        }


class FakeTransport:
    def __init__(self):
        self.uploaded_payload = None
        self.started_hosts = None

    def upload(self, compiled_by_host, *, progress_callback=None):
        self.uploaded_payload = compiled_by_host

    def start_show(self, hosts, *, progress_callback=None):
        self.started_hosts = list(hosts)


class FakeAudioLoader:
    def __init__(self):
        self.loaded_path = None

    def load(self, file_path):
        self.loaded_path = file_path
        return [0.1, 0.2], 44100, file_path


class ProjectScreenControllerTests(unittest.TestCase):
    def test_upload_show_passes_data_through_pipeline(self):
        use_case = FakeUseCase()
        transport = FakeTransport()
        controller = ProjectScreenController(use_case, transport, FakeAudioLoader())

        masters = {"m1": Master(id="m1", name="M", ip="10.0.0.1")}
        controller.upload_show(masters)

        self.assertIs(masters, use_case.called_with)
        self.assertIsNotNone(transport.uploaded_payload)
        self.assertIn("10.0.0.1", transport.uploaded_payload)

    def test_send_start_signal(self):
        transport = FakeTransport()
        controller = ProjectScreenController(
            FakeUseCase(), transport, FakeAudioLoader()
        )

        controller.send_start_signal({"m": Master(id="m", name="x", ip="10.0.0.1")})

        self.assertEqual(["10.0.0.1"], transport.started_hosts)

    def test_load_track(self):
        audio_loader = FakeAudioLoader()
        controller = ProjectScreenController(
            FakeUseCase(), FakeTransport(), audio_loader
        )
        audio, sr, path = controller.load_track("demo.wav")
        self.assertEqual([0.1, 0.2], audio)
        self.assertEqual(44100, sr)
        self.assertEqual("demo.wav", path)
        self.assertEqual("demo.wav", audio_loader.loaded_path)


if __name__ == "__main__":
    unittest.main()
