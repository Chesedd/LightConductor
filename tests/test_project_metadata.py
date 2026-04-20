import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.project_metadata import (
    ProjectMetadata,
)
from lightconductor.application.project_metadata_use_case import (
    ListProjectsWithMetadataUseCase,
)
from lightconductor.infrastructure.project_repository import (
    ProjectRepository,
)


class _MetadataTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.registry_path = self.root / "projects.json"
        self.projects_root = self.root / "Projects"
        self.repo = ProjectRepository(
            projects_json_path=self.registry_path,
            projects_root=self.projects_root,
        )
        self.use_case = ListProjectsWithMetadataUseCase(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_registry_json(self, data):
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(json.dumps(data), encoding="utf-8")

    def _write_registry_raw(self, content):
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(content, encoding="utf-8")

    def _ensure_project_dir(self, name):
        (self.projects_root / name).mkdir(parents=True, exist_ok=True)

    def _write_data_json(self, project_name, payload):
        self._ensure_project_dir(project_name)
        path = self.projects_root / project_name / "data.json"
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _write_audio(self, project_name):
        self._ensure_project_dir(project_name)
        (self.projects_root / project_name / "audio.wav").write_bytes(b"")


class ProjectMetadataUseCaseTests(_MetadataTestBase):
    def test_empty_registry_returns_empty_list(self):
        self.assertEqual(self.use_case.execute(), [])

    def test_registry_with_one_project_no_data_json(self):
        self._write_registry_json(
            {
                "p1": {
                    "id": "p1",
                    "project_name": "Demo",
                    "song_name": "Song",
                    "created_at": "2024-05-01T12:00:00",
                },
            }
        )
        self._ensure_project_dir("Demo")

        result = self.use_case.execute()
        self.assertEqual(len(result), 1)
        meta = result[0]
        self.assertIsInstance(meta, ProjectMetadata)
        self.assertEqual(meta.id, "p1")
        self.assertEqual(meta.project_name, "Demo")
        self.assertEqual(meta.song_name, "Song")
        self.assertEqual(meta.created_at, "2024-05-01T12:00:00")
        self.assertIsNone(meta.modified_at)
        self.assertEqual(meta.masters_count, 0)
        self.assertEqual(meta.slaves_count, 0)
        self.assertFalse(meta.track_present)

    def test_registry_entry_without_matching_dir_is_skipped(self):
        self._write_registry_json(
            {
                "a": {
                    "id": "a",
                    "project_name": "A",
                    "song_name": "sA",
                    "created_at": "2024-01-01T00:00:00",
                },
                "b": {
                    "id": "b",
                    "project_name": "B",
                    "song_name": "sB",
                    "created_at": "2024-01-01T00:00:00",
                },
            }
        )
        self._ensure_project_dir("A")
        # Directory B intentionally missing.
        result = self.use_case.execute()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].project_name, "A")

    def test_counts_from_v1_envelope(self):
        self._write_registry_json(
            {
                "p1": {
                    "id": "p1",
                    "project_name": "Demo",
                    "song_name": "Song",
                    "created_at": "2024-01-01T00:00:00",
                },
            }
        )
        envelope = {
            "schema_version": 1,
            "masters": {
                "m1": {
                    "id": "m1",
                    "name": "Master1",
                    "slaves": {
                        "s1": {"id": "s1"},
                        "s2": {"id": "s2"},
                        "s3": {"id": "s3"},
                    },
                },
                "m2": {
                    "id": "m2",
                    "name": "Master2",
                    "slaves": {
                        "s4": {"id": "s4"},
                        "s5": {"id": "s5"},
                    },
                },
            },
        }
        self._write_data_json("Demo", envelope)

        result = self.use_case.execute()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].masters_count, 2)
        self.assertEqual(result[0].slaves_count, 5)

    def test_counts_from_legacy_pre_envelope_dict(self):
        self._write_registry_json(
            {
                "p1": {
                    "id": "p1",
                    "project_name": "Legacy",
                    "song_name": "Song",
                    "created_at": "2024-01-01T00:00:00",
                },
            }
        )
        legacy = {
            "m1": {
                "id": "m1",
                "slaves": {
                    "s1": {"id": "s1"},
                    "s2": {"id": "s2"},
                },
            },
            "m2": {
                "id": "m2",
                "slaves": {
                    "s3": {"id": "s3"},
                },
            },
        }
        self._write_data_json("Legacy", legacy)

        result = self.use_case.execute()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].masters_count, 2)
        self.assertEqual(result[0].slaves_count, 3)

    def test_counts_zero_on_malformed_data_json(self):
        self._write_registry_json(
            {
                "p1": {
                    "id": "p1",
                    "project_name": "Bad",
                    "song_name": "Song",
                    "created_at": "2024-01-01T00:00:00",
                },
            }
        )
        self._write_data_json("Bad", "{")

        result = self.use_case.execute()
        self.assertEqual(len(result), 1)
        meta = result[0]
        self.assertEqual(meta.masters_count, 0)
        self.assertEqual(meta.slaves_count, 0)
        # File exists on disk, so mtime IS populated.
        self.assertIsNotNone(meta.modified_at)
        # No audio.wav was created.
        self.assertFalse(meta.track_present)

    def test_modified_at_is_iso_string_when_data_json_exists(self):
        self._write_registry_json(
            {
                "p1": {
                    "id": "p1",
                    "project_name": "Demo",
                    "song_name": "Song",
                    "created_at": "2024-01-01T00:00:00",
                },
            }
        )
        self._write_data_json("Demo", {"schema_version": 1, "masters": {}})

        result = self.use_case.execute()
        self.assertEqual(len(result), 1)
        modified_at = result[0].modified_at
        self.assertIsInstance(modified_at, str)
        # Parseable by datetime.fromisoformat.
        parsed = datetime.fromisoformat(modified_at)
        self.assertIsNotNone(parsed)
        # Basic ISO shape check.
        self.assertIn("T", modified_at)
        self.assertTrue(
            any(ch.isdigit() for ch in modified_at),
            f"expected digits in ISO timestamp, got {modified_at!r}",
        )

    def test_track_present_true_when_audio_wav_exists(self):
        self._write_registry_json(
            {
                "p1": {
                    "id": "p1",
                    "project_name": "WithAudio",
                    "song_name": "Song",
                    "created_at": "2024-01-01T00:00:00",
                },
            }
        )
        self._ensure_project_dir("WithAudio")
        self._write_audio("WithAudio")

        result = self.use_case.execute()
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].track_present)

    def test_malformed_registry_entry_skipped_and_logged(self):
        self._write_registry_json(
            {
                "bad": "not-a-dict",
                "good": {
                    "id": "good",
                    "project_name": "Good",
                    "song_name": "sG",
                    "created_at": "2024-01-01T00:00:00",
                },
            }
        )
        self._ensure_project_dir("Good")

        with self.assertLogs(
            "lightconductor.application.project_metadata_use_case",
            level="WARNING",
        ) as cm:
            result = self.use_case.execute()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "good")
        self.assertTrue(
            any("bad" in line for line in cm.output),
            f"expected warning about 'bad' entry, got {cm.output}",
        )

    def test_created_at_preserved_from_registry(self):
        self._write_registry_json(
            {
                "p1": {
                    "id": "p1",
                    "project_name": "Dated",
                    "song_name": "Song",
                    "created_at": "2024-01-15T10:30:00",
                },
                "p2": {
                    "id": "p2",
                    "project_name": "Undated",
                    "song_name": "Song",
                },
            }
        )
        self._ensure_project_dir("Dated")
        self._ensure_project_dir("Undated")

        result = self.use_case.execute()
        by_id = {m.id: m for m in result}
        self.assertEqual(by_id["p1"].created_at, "2024-01-15T10:30:00")
        self.assertIsNone(by_id["p2"].created_at)


if __name__ == "__main__":
    unittest.main()
