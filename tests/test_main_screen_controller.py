import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.presentation import MainScreenController


class FakeRepo:
    def __init__(self):
        self.projects = {}

    def list_projects(self):
        return self.projects.values()

    def save_project(self, project):
        self.projects[project.id] = project

    def delete_project(self, project_id):
        return self.projects.pop(project_id, None) is not None


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


if __name__ == "__main__":
    unittest.main()
