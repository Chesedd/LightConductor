import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.domain.models import Project
from lightconductor.infrastructure.project_repository import (
    ProjectRepository,
)


class _RepoTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.registry_path = self.root / "projects.json"
        self.projects_root = self.root / "Projects"
        self.repo = ProjectRepository(
            projects_json_path=self.registry_path,
            projects_root=self.projects_root,
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _write_registry_raw(self, content):
        self.registry_path.write_text(content, encoding="utf-8")

    def _write_registry_json(self, data):
        self.registry_path.write_text(
            json.dumps(data), encoding="utf-8"
        )

    def _ensure_project_dir(self, name):
        (self.projects_root / name).mkdir(parents=True, exist_ok=True)


class ListProjectsTests(_RepoTestBase):
    def test_list_returns_empty_if_registry_missing(self):
        self.assertEqual(self.repo.list_projects(), [])

    def test_list_returns_empty_if_registry_corrupt(self):
        self._write_registry_raw("{")
        self.assertEqual(self.repo.list_projects(), [])
        # File must NOT be rewritten.
        self.assertEqual(
            self.registry_path.read_text(encoding="utf-8"), "{"
        )

    def test_list_returns_empty_if_registry_not_a_dict(self):
        self._write_registry_json([1, 2, 3])
        self.assertEqual(self.repo.list_projects(), [])

    def test_list_filters_entries_without_directory(self):
        self._write_registry_json({
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
        })
        self._ensure_project_dir("A")
        # Directory for B is missing on purpose.
        projects = self.repo.list_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].id, "a")
        self.assertEqual(projects[0].name, "A")

    def test_list_skips_entries_without_project_name(self):
        self._write_registry_json({
            "x": {"id": "x", "created_at": "2024-01-01T00:00:00"},
        })
        self.assertEqual(self.repo.list_projects(), [])

    def test_list_maps_payload_to_domain_project(self):
        self._write_registry_json({
            "p1": {
                "id": "p1",
                "project_name": "Demo",
                "song_name": "Song",
                "created_at": "2024-01-01T00:00:00",
            },
        })
        self._ensure_project_dir("Demo")
        projects = self.repo.list_projects()
        self.assertEqual(
            projects,
            [Project(id="p1", name="Demo", song_name="Song", masters={})],
        )

    def test_list_defaults_song_name_to_empty_string_if_absent(self):
        self._write_registry_json({
            "p1": {
                "id": "p1",
                "project_name": "Demo",
                "created_at": "2024-01-01T00:00:00",
            },
        })
        self._ensure_project_dir("Demo")
        projects = self.repo.list_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].song_name, "")


class SaveProjectTests(_RepoTestBase):
    def test_save_creates_project_directory_idempotently(self):
        project = Project(id="p1", name="Alpha", song_name="s")
        self.repo.save_project(project)
        # Second save must not raise.
        self.repo.save_project(project)
        self.assertTrue((self.projects_root / "Alpha").is_dir())

    def test_save_registers_project_in_json(self):
        project = Project(id="p1", name="Alpha", song_name="s")
        self.repo.save_project(project)
        self.assertTrue(self.registry_path.exists())
        data = json.loads(
            self.registry_path.read_text(encoding="utf-8")
        )
        self.assertIn("p1", data)
        entry = data["p1"]
        self.assertEqual(entry["id"], "p1")
        self.assertEqual(entry["project_name"], "Alpha")
        self.assertEqual(entry["song_name"], "s")
        self.assertIn("created_at", entry)
        self.assertTrue(entry["created_at"])

    def test_save_preserves_created_at_on_update(self):
        first = Project(id="p1", name="Alpha", song_name="s1")
        self.repo.save_project(first)
        created_at_1 = json.loads(
            self.registry_path.read_text(encoding="utf-8")
        )["p1"]["created_at"]

        time.sleep(0.01)
        second = Project(id="p1", name="Alpha", song_name="s2")
        self.repo.save_project(second)
        entry = json.loads(
            self.registry_path.read_text(encoding="utf-8")
        )["p1"]
        self.assertEqual(entry["created_at"], created_at_1)
        self.assertEqual(entry["song_name"], "s2")

    def test_save_writes_atomically_no_tmp_left(self):
        project = Project(id="p1", name="Alpha", song_name="s")
        self.repo.save_project(project)
        siblings = list(self.registry_path.parent.iterdir())
        self.assertFalse(
            any(p.suffix == ".tmp" for p in siblings),
            f"Unexpected .tmp file among {siblings}",
        )


class DeleteProjectTests(_RepoTestBase):
    def test_delete_returns_false_if_id_not_in_registry(self):
        self.assertFalse(self.repo.delete_project("nope"))

    def test_delete_returns_true_and_removes_entry_and_directory(self):
        project = Project(id="p1", name="A", song_name="s")
        self.repo.save_project(project)
        self.assertTrue((self.projects_root / "A").exists())

        self.assertTrue(self.repo.delete_project("p1"))
        data = json.loads(
            self.registry_path.read_text(encoding="utf-8")
        )
        self.assertNotIn("p1", data)
        self.assertFalse((self.projects_root / "A").exists())

    def test_delete_tolerates_missing_directory(self):
        project = Project(id="p1", name="A", song_name="s")
        self.repo.save_project(project)
        shutil.rmtree(self.projects_root / "A")
        self.assertTrue(self.repo.delete_project("p1"))
        data = json.loads(
            self.registry_path.read_text(encoding="utf-8")
        )
        self.assertNotIn("p1", data)

    def test_delete_does_not_touch_other_projects(self):
        self.repo.save_project(Project(id="p1", name="A", song_name="sA"))
        self.repo.save_project(Project(id="p2", name="B", song_name="sB"))

        self.assertTrue(self.repo.delete_project("p1"))
        data = json.loads(
            self.registry_path.read_text(encoding="utf-8")
        )
        self.assertNotIn("p1", data)
        self.assertIn("p2", data)
        self.assertFalse((self.projects_root / "A").exists())
        self.assertTrue((self.projects_root / "B").exists())


class RenameProjectTests(_RepoTestBase):
    def test_rename_success_renames_dir_and_registry(self):
        self._write_registry_json({
            "p1": {
                "id": "p1",
                "project_name": "Old",
                "song_name": "s",
                "created_at": "2024-01-01T00:00:00",
            },
        })
        self._ensure_project_dir("Old")

        self.assertTrue(self.repo.rename_project("p1", "New"))

        self.assertFalse((self.projects_root / "Old").exists())
        self.assertTrue((self.projects_root / "New").exists())
        data = json.loads(
            self.registry_path.read_text(encoding="utf-8")
        )
        self.assertEqual(data["p1"]["project_name"], "New")
        self.assertEqual(
            data["p1"]["created_at"], "2024-01-01T00:00:00",
        )

    def test_rename_to_same_name_is_noop_success(self):
        self._write_registry_json({
            "p1": {
                "id": "p1",
                "project_name": "Same",
                "song_name": "s",
                "created_at": "2024-01-01T00:00:00",
            },
        })
        self._ensure_project_dir("Same")
        before_bytes = self.registry_path.read_bytes()

        self.assertTrue(self.repo.rename_project("p1", "Same"))

        self.assertEqual(self.registry_path.read_bytes(), before_bytes)
        self.assertTrue((self.projects_root / "Same").exists())

    def test_rename_empty_name_returns_false(self):
        self._write_registry_json({
            "p1": {
                "id": "p1",
                "project_name": "Old",
                "song_name": "s",
                "created_at": "2024-01-01T00:00:00",
            },
        })
        self._ensure_project_dir("Old")
        before_bytes = self.registry_path.read_bytes()

        self.assertFalse(self.repo.rename_project("p1", "   "))

        self.assertEqual(self.registry_path.read_bytes(), before_bytes)
        self.assertTrue((self.projects_root / "Old").exists())

    def test_rename_path_separator_rejected(self):
        self._write_registry_json({
            "p1": {
                "id": "p1",
                "project_name": "Old",
                "song_name": "s",
                "created_at": "2024-01-01T00:00:00",
            },
        })
        self._ensure_project_dir("Old")
        before_bytes = self.registry_path.read_bytes()

        self.assertFalse(self.repo.rename_project("p1", "a/b"))
        self.assertFalse(self.repo.rename_project("p1", "a\\b"))

        self.assertEqual(self.registry_path.read_bytes(), before_bytes)
        self.assertTrue((self.projects_root / "Old").exists())

    def test_rename_collision_with_other_project_returns_false(self):
        self._write_registry_json({
            "p1": {
                "id": "p1",
                "project_name": "Alpha",
                "song_name": "sA",
                "created_at": "2024-01-01T00:00:00",
            },
            "p2": {
                "id": "p2",
                "project_name": "Beta",
                "song_name": "sB",
                "created_at": "2024-01-02T00:00:00",
            },
        })
        self._ensure_project_dir("Alpha")
        self._ensure_project_dir("Beta")
        before_bytes = self.registry_path.read_bytes()

        self.assertFalse(self.repo.rename_project("p1", "Beta"))

        self.assertEqual(self.registry_path.read_bytes(), before_bytes)
        self.assertTrue((self.projects_root / "Alpha").exists())
        self.assertTrue((self.projects_root / "Beta").exists())

    def test_rename_unknown_id_returns_false(self):
        self._write_registry_json({
            "p1": {
                "id": "p1",
                "project_name": "Alpha",
                "song_name": "sA",
                "created_at": "2024-01-01T00:00:00",
            },
        })
        self._ensure_project_dir("Alpha")
        before_bytes = self.registry_path.read_bytes()

        self.assertFalse(self.repo.rename_project("nope", "Gamma"))

        self.assertEqual(self.registry_path.read_bytes(), before_bytes)

    def test_rename_refuses_when_target_dir_exists_without_registry_entry(self):
        self._write_registry_json({
            "p1": {
                "id": "p1",
                "project_name": "Alpha",
                "song_name": "sA",
                "created_at": "2024-01-01T00:00:00",
            },
        })
        self._ensure_project_dir("Alpha")
        # Squatter directory without any registry entry.
        self._ensure_project_dir("Gamma")
        before_bytes = self.registry_path.read_bytes()

        self.assertFalse(self.repo.rename_project("p1", "Gamma"))

        self.assertEqual(self.registry_path.read_bytes(), before_bytes)
        self.assertTrue((self.projects_root / "Alpha").exists())
        self.assertTrue((self.projects_root / "Gamma").exists())


if __name__ == "__main__":
    unittest.main()
