import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lightconductor.domain.models import Tag
from lightconductor.infrastructure.json_mapper import pack_tag, unpack_tag


class PackTagTests(unittest.TestCase):

    def test_pack_tag_minimal_fields(self):
        tag = Tag(time_seconds=0.5, action=True, colors=[[255, 0, 0]])
        self.assertEqual(
            pack_tag(tag),
            {"time": 0.5, "action": True, "colors": [[255, 0, 0]]},
        )

    def test_pack_tag_with_string_action(self):
        tag = Tag(time_seconds=2.0, action="toggle", colors=[[0, 0, 0]])
        packed = pack_tag(tag)
        self.assertEqual(packed["action"], "toggle")
        self.assertIsInstance(packed["action"], str)

    def test_pack_tag_with_empty_colors(self):
        tag = Tag(time_seconds=0.0, action=False, colors=[])
        packed = pack_tag(tag)
        self.assertEqual(packed["colors"], [])

    def test_pack_tag_preserves_int_time(self):
        # time_seconds is type-annotated as float, but dataclass does not
        # validate, and the mapper must not coerce. An int in => an int out.
        tag = Tag(time_seconds=1, action=True, colors=[])
        packed = pack_tag(tag)
        self.assertEqual(packed["time"], 1)
        self.assertIsInstance(packed["time"], int)


class UnpackTagTests(unittest.TestCase):

    def test_unpack_tag_builds_domain_object(self):
        data = {"time": 0.5, "action": True, "colors": [[1, 2, 3]]}
        tag = unpack_tag(data)
        self.assertIsInstance(tag, Tag)
        self.assertEqual(tag.time_seconds, 0.5)
        self.assertIs(tag.action, True)
        self.assertEqual(tag.colors, [[1, 2, 3]])

    def test_unpack_tag_rejects_non_dict(self):
        with self.assertRaises(ValueError) as ctx:
            unpack_tag([1, 2])
        message = str(ctx.exception)
        self.assertIn("tag", message)
        self.assertIn("dict", message)

    def test_unpack_tag_rejects_missing_fields(self):
        data = {"time": 0.5}  # missing action + colors
        with self.assertRaises(ValueError) as ctx:
            unpack_tag(data)
        message = str(ctx.exception)
        self.assertIn("action", message)
        self.assertIn("colors", message)


class RoundTripTests(unittest.TestCase):

    def test_roundtrip_pack_then_unpack(self):
        tag_in = Tag(time_seconds=0.25, action=False, colors=[[10, 20, 30]])
        tag_out = unpack_tag(pack_tag(tag_in))
        self.assertEqual(tag_out, tag_in)


class ProjectManagerDelegationTests(unittest.TestCase):

    def test_project_manager_pack_tag_delegates_to_json_mapper(self):
        # Bypass __init__ (which touches the filesystem for audio + data.json).
        from ProjectScreen.ProjectManager import ProjectManager

        pm = ProjectManager.__new__(ProjectManager)
        ui_like = SimpleNamespace(time=0.7, action=True, colors=[[9, 8, 7]])

        expected = pack_tag(
            Tag(time_seconds=0.7, action=True, colors=[[9, 8, 7]])
        )
        self.assertEqual(pm.packTag(ui_like), expected)


if __name__ == "__main__":
    unittest.main()
