import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.presentation import ProjectScreenController


class FakeMapper:
    def __init__(self):
        self.called_with = None

    def map_masters(self, masters):
        self.called_with = masters
        return {"mapped": True}


class FakeUseCase:
    def __init__(self):
        self.called_with = None

    def execute(self, masters):
        self.called_with = masters
        return {"7": {"3": 4}}, {"7": {100: {"3": {"action": True, "colors": [[255, 0, 0]]}}}}


class FakeTransport:
    def __init__(self):
        self.sent_payload = None
        self.start_sent = False

    def send_payload(self, pins, payload):
        self.sent_payload = (pins, payload)

    def send_start(self):
        self.start_sent = True


class ProjectScreenControllerTests(unittest.TestCase):
    def test_send_show_payload_uses_mapper_use_case_and_transport(self):
        mapper = FakeMapper()
        use_case = FakeUseCase()
        transport = FakeTransport()
        controller = ProjectScreenController(mapper, use_case, transport)

        legacy_masters = {"master-1": object()}
        controller.send_show_payload(legacy_masters)

        self.assertIs(legacy_masters, mapper.called_with)
        self.assertEqual({"mapped": True}, use_case.called_with)
        self.assertIsNotNone(transport.sent_payload)

    def test_send_start_signal(self):
        controller = ProjectScreenController(FakeMapper(), FakeUseCase(), FakeTransport())
        controller.send_start_signal()
        self.assertTrue(controller.transport.start_sent)


if __name__ == "__main__":
    unittest.main()
