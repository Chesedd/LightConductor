import json
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.domain.models import Project
from lightconductor.infrastructure.project_repository import (
    ProjectNameCollision,
    ProjectNotFound,
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


class ExportImportTests(_RepoTestBase):
    VALID_ENVELOPE = {"schema_version": 1, "masters": {}}

    def _seed_project(
        self,
        project_id,
        project_name,
        song_name="song",
        created_at="2024-01-01T00:00:00",
        with_audio=True,
    ):
        self._ensure_project_dir(project_name)
        data_path = (
            self.projects_root / project_name / "data.json"
        )
        data_path.write_text(
            json.dumps(self.VALID_ENVELOPE),
            encoding="utf-8",
        )
        if with_audio:
            (self.projects_root / project_name / "audio.wav").write_bytes(
                b"\x00\x01"
            )
        registry = self.repo._read_registry()
        registry[project_id] = {
            "id": project_id,
            "project_name": project_name,
            "song_name": song_name,
            "created_at": created_at,
        }
        self.repo._write_registry(registry)

    def _build_archive_for(self, project_name, output_zip):
        registry = self.repo._read_registry()
        project_id = next(
            pid
            for pid, payload in registry.items()
            if isinstance(payload, dict)
            and payload.get("project_name") == project_name
        )
        self.repo.export_project_to_archive(project_id, output_zip)
        return output_zip

    def test_export_writes_zip_for_existing_project(self):
        self._seed_project("p1", "Demo")
        out = self.root / "out.zip"
        self.repo.export_project_to_archive("p1", out)
        self.assertTrue(out.exists())
        with zipfile.ZipFile(out, "r") as zf:
            names = set(zf.namelist())
        self.assertIn("manifest.json", names)
        self.assertIn("data.json", names)
        self.assertIn("audio.wav", names)

    def test_export_unknown_id_raises_ProjectNotFound(self):
        out = self.root / "out.zip"
        with self.assertRaises(ProjectNotFound):
            self.repo.export_project_to_archive("nope", out)

    def test_export_missing_project_directory_raises_FileNotFoundError(self):
        self._write_registry_json({
            "g1": {
                "id": "g1",
                "project_name": "Ghost",
                "song_name": "",
                "created_at": "2024-01-01T00:00:00",
            },
        })
        out = self.root / "out.zip"
        with self.assertRaises(FileNotFoundError):
            self.repo.export_project_to_archive("g1", out)

    def test_import_creates_project_directory_and_registry_entry(self):
        self._seed_project(
            "p1", "Demo", song_name="MySong",
            created_at="2024-06-01T12:00:00",
        )
        out = self.root / "demo.zip"
        self._build_archive_for("Demo", out)

        project = self.repo.import_project_from_archive(
            out, "NewProject",
        )
        self.assertEqual(project.name, "NewProject")
        self.assertNotEqual(project.id, "p1")

        new_dir = self.projects_root / "NewProject"
        self.assertTrue(new_dir.exists())
        self.assertTrue((new_dir / "data.json").exists())

        registry = json.loads(
            self.registry_path.read_text(encoding="utf-8")
        )
        self.assertIn(project.id, registry)
        entry = registry[project.id]
        self.assertEqual(entry["project_name"], "NewProject")
        self.assertEqual(entry["song_name"], "MySong")
        self.assertEqual(
            entry["created_at"], "2024-06-01T12:00:00",
        )

    def test_import_without_audio_does_not_create_audio_wav(self):
        self._seed_project("p1", "NoAudio", with_audio=False)
        out = self.root / "noaudio.zip"
        self._build_archive_for("NoAudio", out)

        project = self.repo.import_project_from_archive(
            out, "Imported",
        )
        new_dir = self.projects_root / "Imported"
        self.assertTrue((new_dir / "data.json").exists())
        self.assertFalse((new_dir / "audio.wav").exists())
        self.assertEqual(project.name, "Imported")

    def test_import_collision_raises_ProjectNameCollision(self):
        self._seed_project("p1", "Existing")
        out = self.root / "existing.zip"
        self._build_archive_for("Existing", out)

        before_registry = self.registry_path.read_bytes()
        with self.assertRaises(ProjectNameCollision):
            self.repo.import_project_from_archive(out, "Existing")

        self.assertEqual(
            self.registry_path.read_bytes(), before_registry,
        )

    def test_import_empty_target_name_raises_ValueError(self):
        out = self.root / "anything.zip"
        out.write_bytes(b"\x00")
        before_dirs = set(
            p.name
            for p in self.projects_root.iterdir()
        ) if self.projects_root.exists() else set()
        with self.assertRaises(ValueError):
            self.repo.import_project_from_archive(out, "   ")
        after_dirs = set(
            p.name
            for p in self.projects_root.iterdir()
        ) if self.projects_root.exists() else set()
        self.assertEqual(before_dirs, after_dirs)
        self.assertFalse(self.registry_path.exists())

    def test_import_cleans_up_target_dir_on_registry_write_failure(self):
        self._seed_project("p1", "Source")
        out = self.root / "source.zip"
        self._build_archive_for("Source", out)

        original_write = self.repo._write_registry
        call_count = {"n": 0}

        def failing_write(data):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call is from inside import_project_from_archive
                # (the registry update following extraction).
                raise OSError("simulated registry write failure")
            return original_write(data)

        self.repo._write_registry = failing_write
        try:
            with self.assertRaises(OSError):
                self.repo.import_project_from_archive(out, "Cleanup")
        finally:
            self.repo._write_registry = original_write

        self.assertFalse(
            (self.projects_root / "Cleanup").exists(),
        )

    def test_import_with_path_separator_raises_ValueError(self):
        out = self.root / "anything.zip"
        out.write_bytes(b"\x00")
        with self.assertRaises(ValueError):
            self.repo.import_project_from_archive(out, "a/b")
        with self.assertRaises(ValueError):
            self.repo.import_project_from_archive(out, "a\\b")


if __name__ == "__main__":
    unittest.main()
