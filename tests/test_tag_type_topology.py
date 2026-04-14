import unittest

from ProjectScreen.TagLogic.TagType import TagType


class TagTypeTopologyTests(unittest.TestCase):
    def test_default_topology_is_row_major(self):
        tag_type = TagType("255,255,255", "range", "0", 2, 3)
        self.assertEqual([0, 1, 2, 3, 4, 5], tag_type.topology)

    def test_custom_topology_is_preserved(self):
        tag_type = TagType("255,255,255", "range", "0", 2, 3, topology=[0, 2, 5])
        self.assertEqual([0, 2, 5], tag_type.topology)


if __name__ == "__main__":
    unittest.main()
