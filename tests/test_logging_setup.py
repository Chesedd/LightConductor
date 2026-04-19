import logging
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.infrastructure import logging_setup
from lightconductor.infrastructure.logging_setup import configure_logging


class ConfigureLoggingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self._prev_handlers = list(logging.getLogger().handlers)
        self._prev_level = logging.getLogger().level
        self._prev_excepthook = sys.excepthook
        logging_setup._configured = False
        logging_setup._original_excepthook = None

    def tearDown(self):
        root = logging.getLogger()
        for handler in list(root.handlers):
            if handler not in self._prev_handlers:
                handler.close()
                root.removeHandler(handler)
        root.setLevel(self._prev_level)
        sys.excepthook = self._prev_excepthook
        logging_setup._configured = False
        logging_setup._original_excepthook = None
        self._tmp.cleanup()

    def test_creates_log_file_and_returns_path(self):
        log_path = configure_logging(self.tmp_dir)
        self.assertEqual(log_path, (self.tmp_dir / "lightconductor.log").resolve())
        self.assertTrue(log_path.exists())

    def test_writes_log_line_to_file(self):
        log_path = configure_logging(self.tmp_dir)
        logging.getLogger("lightconductor.test").info("hello")
        for handler in logging.getLogger().handlers:
            handler.flush()
        content = log_path.read_text(encoding="utf-8")
        self.assertIn("hello", content)

    def test_idempotent_does_not_duplicate_handlers(self):
        configure_logging(self.tmp_dir)
        first_count = len(logging.getLogger().handlers)
        configure_logging(self.tmp_dir)
        second_count = len(logging.getLogger().handlers)
        self.assertEqual(first_count, second_count)


if __name__ == "__main__":
    unittest.main()
