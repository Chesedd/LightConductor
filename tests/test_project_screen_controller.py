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
        compiled = {}
        for master in masters.values():
            compiled.setdefault(master.ip, []).append(
                CompiledSlaveShow(
                    master_ip=master.ip,
                    slave_id=1,
                    total_led_count=0,
                    blob=b"",
                )
            )
        return compiled


class FakeTransport:
    def __init__(self):
        self.uploaded_payload = None
        self.uploaded_progress_callback = None
        self.upload_call_count = 0
        self.started_hosts = None

    def upload(self, compiled_by_host, *, progress_callback=None):
        self.uploaded_payload = compiled_by_host
        self.uploaded_progress_callback = progress_callback
        self.upload_call_count += 1

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

    def test_upload_show_with_none_selection_uploads_all(self):
        use_case = FakeUseCase()
        transport = FakeTransport()
        controller = ProjectScreenController(use_case, transport, FakeAudioLoader())

        masters = {
            "id_a": Master(id="id_a", name="A", ip="10.0.0.1"),
            "id_b": Master(id="id_b", name="B", ip="10.0.0.2"),
        }
        controller.upload_show(masters, selected_master_ids=None)

        self.assertEqual(masters, use_case.called_with)
        self.assertIn("10.0.0.1", transport.uploaded_payload)
        self.assertIn("10.0.0.2", transport.uploaded_payload)

    def test_upload_show_with_subset_selection_filters_masters(self):
        use_case = FakeUseCase()
        transport = FakeTransport()
        controller = ProjectScreenController(use_case, transport, FakeAudioLoader())

        masters = {
            "id_a": Master(id="id_a", name="A", ip="10.0.0.1"),
            "id_b": Master(id="id_b", name="B", ip="10.0.0.2"),
        }
        controller.upload_show(masters, selected_master_ids={"id_a"})

        self.assertEqual({"id_a": masters["id_a"]}, use_case.called_with)
        self.assertIn("10.0.0.1", transport.uploaded_payload)
        self.assertNotIn("10.0.0.2", transport.uploaded_payload)

    def test_upload_show_with_empty_selection_is_noop(self):
        use_case = FakeUseCase()
        transport = FakeTransport()
        controller = ProjectScreenController(use_case, transport, FakeAudioLoader())

        masters = {
            "id_a": Master(id="id_a", name="A", ip="10.0.0.1"),
            "id_b": Master(id="id_b", name="B", ip="10.0.0.2"),
        }
        controller.upload_show(masters, selected_master_ids=set())

        self.assertEqual({}, use_case.called_with)
        self.assertEqual({}, transport.uploaded_payload)
        self.assertEqual(1, transport.upload_call_count)

    def test_upload_show_unknown_id_in_selection_silently_dropped(self):
        use_case = FakeUseCase()
        transport = FakeTransport()
        controller = ProjectScreenController(use_case, transport, FakeAudioLoader())

        masters = {
            "id_a": Master(id="id_a", name="A", ip="10.0.0.1"),
            "id_b": Master(id="id_b", name="B", ip="10.0.0.2"),
        }
        controller.upload_show(
            masters,
            selected_master_ids={"id_a", "id_unknown"},
        )

        self.assertEqual({"id_a": masters["id_a"]}, use_case.called_with)

    def test_upload_show_progress_callback_passed_through(self):
        use_case = FakeUseCase()
        transport = FakeTransport()
        controller = ProjectScreenController(use_case, transport, FakeAudioLoader())

        masters = {
            "id_a": Master(id="id_a", name="A", ip="10.0.0.1"),
            "id_b": Master(id="id_b", name="B", ip="10.0.0.2"),
        }

        def cb(sent, total):
            return True

        controller.upload_show(
            masters,
            selected_master_ids={"id_a"},
            progress_callback=cb,
        )

        self.assertIs(cb, transport.uploaded_progress_callback)


if __name__ == "__main__":
    unittest.main()
