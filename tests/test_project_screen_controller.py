import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.compiled_show import CompiledSlaveShow
from lightconductor.presentation import ProjectScreenController


class FakeMapper:
    def __init__(self):
        self.called_with = None
        self.map_masters_return_value = {"m1": SimpleNamespace(ip="10.0.0.1")}

    def map_masters(self, masters):
        self.called_with = masters
        return self.map_masters_return_value


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

    def upload(self, compiled_by_host):
        self.uploaded_payload = compiled_by_host

    def start_show(self, hosts):
        self.started_hosts = list(hosts)


class FakeAudioLoader:
    def __init__(self):
        self.loaded_path = None

    def load(self, file_path):
        self.loaded_path = file_path
        return [0.1, 0.2], 44100, file_path


class ProjectScreenControllerTests(unittest.TestCase):
    def test_upload_show_passes_data_through_pipeline(self):
        mapper = FakeMapper()
        use_case = FakeUseCase()
        transport = FakeTransport()
        controller = ProjectScreenController(mapper, use_case, transport, FakeAudioLoader())

        legacy_masters = {"master-1": object()}
        controller.upload_show(legacy_masters)

        self.assertIs(legacy_masters, mapper.called_with)
        self.assertIs(mapper.map_masters_return_value, use_case.called_with)
        self.assertIsNotNone(transport.uploaded_payload)
        self.assertIn("10.0.0.1", transport.uploaded_payload)

    def test_send_start_signal(self):
        mapper = FakeMapper()
        transport = FakeTransport()
        controller = ProjectScreenController(mapper, FakeUseCase(), transport, FakeAudioLoader())

        controller.send_start_signal({"master-1": object()})

        self.assertEqual(["10.0.0.1"], transport.started_hosts)

    def test_load_track(self):
        audio_loader = FakeAudioLoader()
        controller = ProjectScreenController(FakeMapper(), FakeUseCase(), FakeTransport(), audio_loader)
        audio, sr, path = controller.load_track("demo.wav")
        self.assertEqual([0.1, 0.2], audio)
        self.assertEqual(44100, sr)
        self.assertEqual("demo.wav", path)
        self.assertEqual("demo.wav", audio_loader.loaded_path)


if __name__ == "__main__":
    unittest.main()
