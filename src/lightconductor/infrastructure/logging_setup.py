import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3

_configured = False
_original_excepthook = None


def _repo_root() -> Path:
    # src/lightconductor/infrastructure/logging_setup.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3]


def configure_logging(log_dir: Optional[Path] = None) -> Path:
    global _configured, _original_excepthook

    if log_dir is None:
        log_dir = _repo_root() / "logs"
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = (log_dir / "lightconductor.log").resolve()

    if _configured:
        return log_path

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

    _original_excepthook = sys.excepthook

    def _excepthook(exc_type, exc_value, exc_tb):
        logging.getLogger(__name__).critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        if _original_excepthook is not None:
            _original_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    _configured = True
    return log_path
