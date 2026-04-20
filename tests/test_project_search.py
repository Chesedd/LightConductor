import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.project_search import (
    MasterVisibility,
    SlaveVisibility,
    compute_visibility,
)
from lightconductor.domain.models import Master, Slave, TagType


def _make_simple_tree(masters_spec):
    """Takes a structure like
       { "m1": {"name": "Alpha", "slaves": {
             "s1": {"name": "Front",
                    "tag_types": ["flash", "fill"]},
       }}}
    Returns Dict[str, Master] with domain objects."""
    tree = {}
    for master_id, m_spec in masters_spec.items():
        master = Master(id=master_id, name=m_spec["name"])
        for slave_id, s_spec in m_spec.get("slaves", {}).items():
            slave = Slave(
                id=slave_id,
                name=s_spec["name"],
                pin=str(s_spec.get("pin", "0")),
                led_count=int(s_spec.get("led_count", 0)),
            )
            for type_name in s_spec.get("tag_types", []):
                slave.tag_types[type_name] = TagType(
                    name=type_name,
                    pin="0",
                    rows=1,
                    columns=1,
                )
            master.slaves[slave_id] = slave
        tree[master_id] = master
    return tree


class ComputeVisibilityTests(unittest.TestCase):
    def test_empty_query_everything_visible(self):
        tree = _make_simple_tree({
            "m1": {"name": "Alpha", "slaves": {
                "s1": {"name": "Front", "tag_types": ["flash", "fill"]},
                "s2": {"name": "Back", "tag_types": ["strobe", "glow"]},
            }},
            "m2": {"name": "Beta", "slaves": {
                "s3": {"name": "Top", "tag_types": ["a", "b"]},
                "s4": {"name": "Bottom", "tag_types": ["c", "d"]},
            }},
        })
        result = compute_visibility(tree, "")
        self.assertEqual(set(result.keys()), {"m1", "m2"})
        for mv in result.values():
            self.assertIsInstance(mv, MasterVisibility)
            self.assertTrue(mv.visible)
            for sv in mv.slaves.values():
                self.assertIsInstance(sv, SlaveVisibility)
                self.assertTrue(sv.visible)
                for visible in sv.tag_types.values():
                    self.assertTrue(visible)

    def test_query_matching_master_name_shows_full_subtree(self):
        # Cascade is UP-only. A master-name match does NOT propagate
        # visibility down to the slaves or tag types. The master
        # itself is the only visible node.
        tree = _make_simple_tree({
            "m1": {"name": "Stage", "slaves": {
                "s1": {"name": "Front", "tag_types": ["flash", "fill"]},
            }},
        })
        result = compute_visibility(tree, "stage")
        mv = result["m1"]
        self.assertTrue(mv.visible)
        sv = mv.slaves["s1"]
        self.assertFalse(sv.visible)
        self.assertEqual(sv.tag_types, {"flash": False, "fill": False})

    def test_query_matching_tag_type_cascades_up(self):
        tree = _make_simple_tree({
            "m1": {"name": "Stage", "slaves": {
                "s1": {"name": "Front", "tag_types": ["flash"]},
            }},
        })
        result = compute_visibility(tree, "flash")
        mv = result["m1"]
        self.assertTrue(mv.visible)
        sv = mv.slaves["s1"]
        self.assertTrue(sv.visible)
        self.assertTrue(sv.tag_types["flash"])

    def test_query_matching_slave_shows_master_but_siblings_hidden(self):
        tree = _make_simple_tree({
            "m1": {"name": "Stage", "slaves": {
                "s1": {"name": "Front", "tag_types": ["glow"]},
                "s2": {"name": "Back", "tag_types": ["strobe"]},
            }},
        })
        result = compute_visibility(tree, "front")
        mv = result["m1"]
        self.assertTrue(mv.visible)
        self.assertTrue(mv.slaves["s1"].visible)
        self.assertFalse(mv.slaves["s2"].visible)
        self.assertFalse(mv.slaves["s1"].tag_types["glow"])
        self.assertFalse(mv.slaves["s2"].tag_types["strobe"])

    def test_case_insensitive_match(self):
        tree = _make_simple_tree({
            "m1": {"name": "Stage", "slaves": {
                "s1": {"name": "Front", "tag_types": ["flash"]},
            }},
        })
        for q in ("FLASH", "Flash", "fLaSh"):
            result = compute_visibility(tree, q)
            self.assertTrue(result["m1"].slaves["s1"].tag_types["flash"])
        for q in ("stage", "STAGE", "sTaGe"):
            result = compute_visibility(tree, q)
            self.assertTrue(result["m1"].visible)

    def test_whitespace_in_query_stripped(self):
        tree = _make_simple_tree({
            "m1": {"name": "Stage", "slaves": {
                "s1": {"name": "Front", "tag_types": ["flash"]},
            }},
        })
        result = compute_visibility(tree, "   flash   ")
        self.assertTrue(result["m1"].slaves["s1"].tag_types["flash"])
        self.assertTrue(result["m1"].slaves["s1"].visible)
        self.assertTrue(result["m1"].visible)

    def test_empty_tree_returns_empty_dict(self):
        self.assertEqual(compute_visibility({}, "anything"), {})

    def test_query_substring_match(self):
        tree = _make_simple_tree({
            "m1": {"name": "Stage", "slaves": {
                "s1": {"name": "Front",
                       "tag_types": ["headlight_flash"]},
            }},
        })
        for q in ("light", "head", "flash"):
            result = compute_visibility(tree, q)
            mv = result["m1"]
            sv = mv.slaves["s1"]
            self.assertTrue(sv.tag_types["headlight_flash"])
            self.assertTrue(sv.visible)
            self.assertTrue(mv.visible)

    def test_no_match_hides_everything_except_empty_empty_query(self):
        tree = _make_simple_tree({
            "m1": {"name": "Stage", "slaves": {
                "s1": {"name": "Front", "tag_types": ["flash", "fill"]},
                "s2": {"name": "Back", "tag_types": ["strobe"]},
            }},
            "m2": {"name": "Booth", "slaves": {
                "s3": {"name": "Top", "tag_types": ["glow"]},
            }},
        })
        result = compute_visibility(tree, "xyzzy")
        for mv in result.values():
            self.assertFalse(mv.visible)
            for sv in mv.slaves.values():
                self.assertFalse(sv.visible)
                for visible in sv.tag_types.values():
                    self.assertFalse(visible)

    def test_multiple_masters_some_match_some_dont(self):
        tree = _make_simple_tree({
            "m1": {"name": "Alpha", "slaves": {
                "s1": {"name": "Front", "tag_types": ["flash"]},
            }},
            "m2": {"name": "Beta", "slaves": {
                "s2": {"name": "Back", "tag_types": ["glow"]},
            }},
        })
        result = compute_visibility(tree, "flash")
        self.assertTrue(result["m1"].visible)
        self.assertTrue(result["m1"].slaves["s1"].visible)
        self.assertFalse(result["m2"].visible)
        self.assertFalse(result["m2"].slaves["s2"].visible)

    def test_slave_with_no_tag_types_matches_by_own_name(self):
        tree = _make_simple_tree({
            "m1": {"name": "Stage", "slaves": {
                "s1": {"name": "Front", "tag_types": []},
            }},
        })
        result = compute_visibility(tree, "front")
        mv = result["m1"]
        sv = mv.slaves["s1"]
        self.assertTrue(sv.visible)
        self.assertTrue(mv.visible)
        self.assertEqual(sv.tag_types, {})

    def test_tag_type_visibility_dict_contains_every_type_key(self):
        tree = _make_simple_tree({
            "m1": {"name": "Stage", "slaves": {
                "s1": {"name": "Front", "tag_types": ["a", "b", "c"]},
            }},
        })
        result = compute_visibility(tree, "a")
        sv = result["m1"].slaves["s1"]
        self.assertEqual(set(sv.tag_types.keys()), {"a", "b", "c"})
        self.assertTrue(sv.tag_types["a"])
        self.assertFalse(sv.tag_types["b"])
        self.assertFalse(sv.tag_types["c"])


if __name__ == "__main__":
    unittest.main()
