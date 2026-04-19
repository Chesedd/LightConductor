from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

BACKUP_COUNT = 3


def backup_path(data_path: Path, index: int) -> Path:
    """Return the path of the Nth backup for `data_path`.

    index=1 is the most recent backup, index=BACKUP_COUNT the oldest.
    """
    return data_path.with_name(f"{data_path.name}.bak.{index}")


def rotate_backups(
    data_path: Path,
    *,
    backup_count: int = BACKUP_COUNT,
) -> None:
    """Rotate `.bak.N` snapshots for `data_path` and copy the current
    file (if present) into `.bak.1`.

    Best-effort: any OSError during rotation is logged via
    ``logger.exception`` but not re-raised, so a failing rotation does
    not block the subsequent write of `data_path` itself.
    """
    if backup_count <= 0:
        return

    try:
        oldest = backup_path(data_path, backup_count)
        if oldest.exists():
            oldest.unlink()

        for i in range(backup_count, 1, -1):
            src = backup_path(data_path, i - 1)
            dst = backup_path(data_path, i)
            if src.exists():
                os.replace(src, dst)

        if data_path.exists():
            shutil.copy2(data_path, backup_path(data_path, 1))
    except OSError:
        logger.exception(
            "Backup rotation failed for %s; continuing with write", data_path
        )


def write_with_rotation(
    data_path: Path,
    content: bytes,
    *,
    backup_count: int = BACKUP_COUNT,
) -> None:
    """Atomically write `content` to `data_path` after rotating backups.

    Backups are rotated best-effort via :func:`rotate_backups`. The new
    content is written to a sibling ``.tmp`` file, flushed and fsynced,
    then swapped into place via :func:`os.replace`, which is atomic on
    POSIX and Windows (Python 3.3+). The temp file is removed if the
    write phase fails; the exception is re-raised.
    """
    rotate_backups(data_path, backup_count=backup_count)

    tmp_path = data_path.with_name(data_path.name + ".tmp")
    try:
        with open(tmp_path, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, data_path)
    except BaseException:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            logger.exception("Failed to clean up temp file %s", tmp_path)
        raise
