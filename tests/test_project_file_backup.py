import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.infrastructure.project_file_backup import (
    BACKUP_COUNT,
    backup_path,
    rotate_backups,
    write_with_rotation,
)


class ProjectFileBackupTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.path = self.tmp / "data.json"

    def tearDown(self):
        try:
            os.chmod(self.tmp, 0o700)
        except OSError:
            pass
        self._tmp.cleanup()

    def _list_tmp_files(self):
        return [p for p in self.tmp.iterdir() if p.suffix == ".tmp"]

    def test_backup_count_constant(self):
        self.assertEqual(BACKUP_COUNT, 3)

    def test_first_write_creates_file_and_no_backups(self):
        write_with_rotation(self.path, b"v1")
        self.assertEqual(self.path.read_bytes(), b"v1")
        for i in range(1, BACKUP_COUNT + 1):
            self.assertFalse(backup_path(self.path, i).exists())

    def test_second_write_creates_bak_1(self):
        write_with_rotation(self.path, b"v1")
        write_with_rotation(self.path, b"v2")
        self.assertEqual(self.path.read_bytes(), b"v2")
        self.assertEqual(backup_path(self.path, 1).read_bytes(), b"v1")
        self.assertFalse(backup_path(self.path, 2).exists())
        self.assertFalse(backup_path(self.path, 3).exists())

    def test_rotation_up_to_backup_count(self):
        for i in range(1, 6):
            write_with_rotation(self.path, f"v{i}".encode())
        self.assertEqual(self.path.read_bytes(), b"v5")
        self.assertEqual(backup_path(self.path, 1).read_bytes(), b"v4")
        self.assertEqual(backup_path(self.path, 2).read_bytes(), b"v3")
        self.assertEqual(backup_path(self.path, 3).read_bytes(), b"v2")
        self.assertFalse(backup_path(self.path, 4).exists())

    def test_no_tmp_file_left_behind_on_success(self):
        write_with_rotation(self.path, b"v1")
        write_with_rotation(self.path, b"v2")
        self.assertEqual(self._list_tmp_files(), [])

    def test_tmp_file_cleaned_on_write_failure(self):
        write_with_rotation(self.path, b"v1")

        def boom(*args, **kwargs):
            raise OSError("simulated replace failure")

        with mock.patch(
            "lightconductor.infrastructure.project_file_backup.os.replace",
            side_effect=boom,
        ):
            with self.assertRaises(OSError):
                write_with_rotation(self.path, b"v2")

        self.assertEqual(self._list_tmp_files(), [])
        self.assertEqual(self.path.read_bytes(), b"v1")

    def test_backup_count_zero_disables_rotation(self):
        write_with_rotation(self.path, b"v1", backup_count=0)
        write_with_rotation(self.path, b"v2", backup_count=0)
        self.assertEqual(self.path.read_bytes(), b"v2")
        for i in range(1, BACKUP_COUNT + 1):
            self.assertFalse(backup_path(self.path, i).exists())

    def test_backup_is_byte_copy_not_reserialized(self):
        raw = b'{"this_is_not_json'
        self.path.write_bytes(raw)
        write_with_rotation(self.path, b"new valid content")
        self.assertEqual(backup_path(self.path, 1).read_bytes(), raw)
        self.assertEqual(self.path.read_bytes(), b"new valid content")

    def test_rotation_skips_missing_intermediate_backup(self):
        self.path.write_bytes(b"current")
        backup_path(self.path, 2).write_bytes(b"old2")
        self.assertFalse(backup_path(self.path, 1).exists())

        write_with_rotation(self.path, b"new")

        self.assertEqual(self.path.read_bytes(), b"new")
        self.assertEqual(backup_path(self.path, 1).read_bytes(), b"current")
        self.assertFalse(backup_path(self.path, 2).exists())
        self.assertEqual(backup_path(self.path, 3).read_bytes(), b"old2")

    def test_rotate_without_existing_data_path(self):
        backup_path(self.path, 1).write_bytes(b"old")
        self.assertFalse(self.path.exists())

        rotate_backups(self.path)

        self.assertFalse(backup_path(self.path, 1).exists())
        self.assertEqual(backup_path(self.path, 2).read_bytes(), b"old")
        self.assertFalse(self.path.exists())

    def test_rotation_failure_is_swallowed_and_logged(self):
        write_with_rotation(self.path, b"v1")

        def boom(*args, **kwargs):
            raise OSError("simulated copy failure")

        with mock.patch(
            "lightconductor.infrastructure.project_file_backup.shutil.copy2",
            side_effect=boom,
        ):
            with self.assertLogs(
                "lightconductor.infrastructure.project_file_backup",
                level="ERROR",
            ):
                write_with_rotation(self.path, b"v2")

        self.assertEqual(self.path.read_bytes(), b"v2")

    def test_os_replace_atomicity_smoke(self):
        # os.replace is atomic on POSIX and Windows (Python 3.3+): a
        # concurrent reader sees either the old file or the new one,
        # never a partial write. We cannot race here, but we assert
        # the contract's observable invariant: after a successful call
        # the target exists, contains the full payload, and no stray
        # .tmp sidecar remains.
        write_with_rotation(self.path, b"v1")
        self.assertTrue(self.path.exists())
        self.assertEqual(self.path.read_bytes(), b"v1")
        self.assertEqual(self._list_tmp_files(), [])


if __name__ == "__main__":
    unittest.main()
