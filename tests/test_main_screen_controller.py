import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor import presentation
from lightconductor.config import AppSettings
from lightconductor.infrastructure.project_archive import (
    ArchiveReadError,
)
from lightconductor.presentation import MainScreenController


class FakeRepo:
    def __init__(self):
        self.projects = {}
        self.registry = {}  # project_id -> payload dict

    def list_projects(self):
        return self.projects.values()

    def save_project(self, project):
        self.projects[project.id] = project
        self.registry[project.id] = {
            "id": project.id,
            "project_name": project.name,
            "song_name": project.song_name,
            "created_at": "2024-01-01T00:00:00",
        }

    def delete_project(self, project_id):
        self.registry.pop(project_id, None)
        return self.projects.pop(project_id, None) is not None

    def rename_project(self, project_id, new_name):
        # Not exercised by these tests but present for
        # protocol compliance.
        p = self.projects.get(project_id)
        if p is None:
            return False
        p.name = new_name
        if project_id in self.registry:
            self.registry[project_id]["project_name"] = new_name
        return True

    def read_registry(self):
        return dict(self.registry)

    def data_json_path(self, project_name):
        return f"/fake/{project_name}/data.json"

    def audio_exists(self, project_name):
        return False

    def project_dir_exists(self, project_name):
        return project_name in {p.name for p in self.projects.values()}

    def export_project_to_archive(
        self,
        project_id,
        output_zip_path,
    ):
        self.last_export = (project_id, str(output_zip_path))

    def import_project_from_archive(
        self,
        zip_path,
        target_project_name,
    ):
        from lightconductor.domain.models import Project

        p = Project(
            id="imported-id",
            name=target_project_name,
            song_name="imported-song",
        )
        self.projects[p.id] = p
        self.registry[p.id] = {
            "id": p.id,
            "project_name": p.name,
            "song_name": p.song_name,
            "created_at": "2025-01-01T00:00:00",
        }
        return p


class MainScreenControllerTests(unittest.TestCase):
    def test_create_list_delete_project(self):
        repo = FakeRepo()
        controller = MainScreenController(repo)

        created = controller.create_project("Demo", "Song")
        self.assertEqual("Demo", created["project_name"])

        listed = controller.list_projects()
        self.assertEqual(1, len(listed))
        self.assertEqual(created["id"], listed[0]["id"])

        deleted = controller.delete_project(created["id"])
        self.assertTrue(deleted)
        self.assertEqual([], controller.list_projects())


class ExportImportControllerTests(unittest.TestCase):
    def test_controller_export_project_delegates_to_repo(self):
        repo = FakeRepo()
        controller = MainScreenController(repo)
        controller.export_project("p1", "/tmp/x.zip")
        self.assertEqual(repo.last_export, ("p1", "/tmp/x.zip"))

    def test_controller_import_project_returns_dict(self):
        repo = FakeRepo()
        controller = MainScreenController(repo)
        result = controller.import_project("/tmp/x.zip", "Imported")
        self.assertEqual(
            result,
            {
                "id": "imported-id",
                "project_name": "Imported",
                "song_name": "imported-song",
            },
        )


class InspectArchiveManifestTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _write_valid_archive(self, zip_path: Path) -> dict:
        manifest = {
            "manifest_version": 1,
            "exported_at": "2025-01-01T00:00:00+00:00",
            "source_project_name": "SourceProj",
            "song_name": "SourceSong",
            "source_created_at": "2024-06-15T10:00:00",
            "data_schema_version": 1,
            "has_audio": False,
        }
        envelope = {"schema_version": 1, "masters": {}}
        with zipfile.ZipFile(
            zip_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            zf.writestr(
                "manifest.json",
                json.dumps(manifest, indent=2).encode("utf-8"),
            )
            zf.writestr(
                "data.json",
                json.dumps(envelope, indent=2).encode("utf-8"),
            )
        return manifest

    def test_inspect_archive_manifest_returns_fields(self):
        repo = FakeRepo()
        controller = MainScreenController(repo)
        zip_path = self.tmp / "archive.zip"
        manifest = self._write_valid_archive(zip_path)
        result = controller.inspect_archive_manifest(zip_path)
        self.assertEqual(
            set(result.keys()),
            {
                "source_project_name",
                "song_name",
                "source_created_at",
                "has_audio",
            },
        )
        self.assertEqual(
            result["source_project_name"],
            manifest["source_project_name"],
        )
        self.assertEqual(
            result["song_name"],
            manifest["song_name"],
        )
        self.assertEqual(
            result["source_created_at"],
            manifest["source_created_at"],
        )
        self.assertEqual(
            result["has_audio"],
            manifest["has_audio"],
        )

    def test_inspect_archive_manifest_propagates_archive_error(self):
        repo = FakeRepo()
        controller = MainScreenController(repo)
        bogus = self.tmp / "not-a-zip.zip"
        bogus.write_text("this is not a zip file")
        with self.assertRaises(ArchiveReadError):
            controller.inspect_archive_manifest(bogus)


class RecentProjectsTests(unittest.TestCase):
    def setUp(self):
        self._orig_save = presentation.main_controller.save_settings
        presentation.main_controller.save_settings = lambda *_a, **_kw: None

    def tearDown(self):
        presentation.main_controller.save_settings = self._orig_save

    def test_mark_project_opened_with_no_settings_is_noop(self):
        repo = FakeRepo()
        controller = MainScreenController(repo)
        controller.mark_project_opened("pX")
        self.assertIsNone(controller.settings)

    def test_mark_project_opened_moves_id_to_front(self):
        repo = FakeRepo()
        settings = AppSettings(recent_project_ids=["p2", "p3"])
        controller = MainScreenController(repo, settings=settings)
        controller.mark_project_opened("p1")
        self.assertEqual(
            settings.recent_project_ids,
            ["p1", "p2", "p3"],
        )

    def test_mark_project_opened_dedupes_existing_id(self):
        repo = FakeRepo()
        settings = AppSettings(
            recent_project_ids=["p1", "p2", "p3"],
        )
        controller = MainScreenController(repo, settings=settings)
        controller.mark_project_opened("p2")
        self.assertEqual(
            settings.recent_project_ids,
            ["p2", "p1", "p3"],
        )

    def test_mark_project_opened_truncates_to_limit(self):
        repo = FakeRepo()
        settings = AppSettings(
            recent_project_ids=["p1", "p2", "p3", "p4", "p5"],
        )
        controller = MainScreenController(repo, settings=settings)
        controller.mark_project_opened("p6")
        self.assertEqual(len(settings.recent_project_ids), 5)
        self.assertEqual(settings.recent_project_ids[0], "p6")
        self.assertNotIn("p5", settings.recent_project_ids)

    def test_delete_project_prunes_recent(self):
        repo = FakeRepo()
        settings = AppSettings()
        controller = MainScreenController(repo, settings=settings)
        created = controller.create_project("Demo", "Song")
        controller.mark_project_opened(created["id"])
        self.assertIn(created["id"], settings.recent_project_ids)
        deleted = controller.delete_project(created["id"])
        self.assertTrue(deleted)
        self.assertNotIn(
            created["id"],
            settings.recent_project_ids,
        )

    def test_get_recent_projects_filters_stale_ids(self):
        repo = FakeRepo()
        settings = AppSettings(
            recent_project_ids=["ghost", "p1"],
        )
        controller = MainScreenController(repo, settings=settings)
        created = controller.create_project("RealProj", "Song")
        # Replace the recent list to include the ghost and the
        # real id (in that order).
        settings.recent_project_ids = ["ghost", created["id"]]
        result = controller.get_recent_projects()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], created["id"])
        # get does NOT mutate persistence.
        self.assertEqual(
            settings.recent_project_ids,
            ["ghost", created["id"]],
        )


if __name__ == "__main__":
    unittest.main()
