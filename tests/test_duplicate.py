import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.commands import (
    AddMasterCommand,
    AddSlaveCommand,
    AddTagCommand,
    AddTagTypeCommand,
    CommandStack,
    CompositeCommand,
)
from lightconductor.application.duplicate import (
    build_duplicate_master_composite,
    build_duplicate_slave_composite,
    deep_copy_master,
    deep_copy_slave,
    resolve_copy_name,
)
from lightconductor.application.project_state import ProjectState
from lightconductor.domain.models import Master, Slave, Tag, TagType


def _counter_id_factory():
    """Deterministic id factory for testing."""
    state = {"n": 0}

    def _next():
        state["n"] += 1
        return f"id{state['n']:06d}"

    return _next


def _build_state_with_one_master():
    """Minimal Master/Slave/TagType/Tag tree for tests.
    id strings human-readable, not timestamps."""
    state = ProjectState()
    master = Master(id="m_src", name="Stage")
    state.add_master(master)
    state.add_slave(
        "m_src",
        Slave(id="s_src_1", name="Left", pin="0", led_count=30),
    )
    state.add_slave(
        "m_src",
        Slave(id="s_src_2", name="Right", pin="1", led_count=45),
    )
    state.add_tag_type(
        "m_src", "s_src_1",
        TagType(
            name="alpha", pin="0", rows=1, columns=2,
            color=[10, 20, 30], topology=[0, 1],
        ),
    )
    state.add_tag_type(
        "m_src", "s_src_1",
        TagType(
            name="beta", pin="2", rows=2, columns=1,
            color="red", topology=[2, 3],
        ),
    )
    state.add_tag(
        "m_src", "s_src_1", "alpha",
        Tag(time_seconds=0.5, action=True, colors=[[1, 2, 3]]),
    )
    state.add_tag(
        "m_src", "s_src_1", "alpha",
        Tag(time_seconds=1.5, action=False, colors=[[4, 5, 6]]),
    )
    state.add_tag(
        "m_src", "s_src_1", "beta",
        Tag(time_seconds=2.0, action="toggle", colors=[]),
    )
    return state


class ResolveCopyNameTests(unittest.TestCase):
    def test_resolve_copy_name_unique_returns_copy_suffix(self):
        self.assertEqual(
            resolve_copy_name("Stage", ["Other"]),
            "Stage (copy)",
        )

    def test_resolve_copy_name_first_collision_returns_copy_2(self):
        self.assertEqual(
            resolve_copy_name("Stage", ["Stage", "Stage (copy)"]),
            "Stage (copy 2)",
        )

    def test_resolve_copy_name_multiple_collisions_finds_next_suffix(self):
        existing = ["Stage (copy)", "Stage (copy 2)", "Stage (copy 3)"]
        self.assertEqual(
            resolve_copy_name("Stage", existing),
            "Stage (copy 4)",
        )

    def test_resolve_copy_name_empty_existing_returns_copy(self):
        self.assertEqual(
            resolve_copy_name("Stage", []),
            "Stage (copy)",
        )


class DeepCopyTests(unittest.TestCase):
    def test_deep_copy_master_shares_no_refs(self):
        state = _build_state_with_one_master()
        source = state.master("m_src")

        dup = deep_copy_master(source)

        self.assertIsNot(dup, source)
        self.assertIsNot(dup.slaves, source.slaves)
        for slave_id, dup_slave in dup.slaves.items():
            src_slave = source.slaves[slave_id]
            self.assertIsNot(dup_slave, src_slave)
            self.assertIsNot(dup_slave.tag_types, src_slave.tag_types)
            for type_name, dup_tt in dup_slave.tag_types.items():
                src_tt = src_slave.tag_types[type_name]
                self.assertIsNot(dup_tt, src_tt)
                self.assertIsNot(dup_tt.tags, src_tt.tags)
                for i, dup_tag in enumerate(dup_tt.tags):
                    self.assertIsNot(dup_tag, src_tt.tags[i])

    def test_deep_copy_slave_shares_no_refs(self):
        state = _build_state_with_one_master()
        source = state.master("m_src").slaves["s_src_1"]

        dup = deep_copy_slave(source)

        self.assertIsNot(dup, source)
        self.assertIsNot(dup.tag_types, source.tag_types)
        for type_name, dup_tt in dup.tag_types.items():
            src_tt = source.tag_types[type_name]
            self.assertIsNot(dup_tt, src_tt)
            self.assertIsNot(dup_tt.tags, src_tt.tags)

    def test_deep_copy_master_does_not_mutate_source(self):
        state = _build_state_with_one_master()
        source = state.master("m_src")
        src_name = source.name
        src_slave_count = len(source.slaves)
        src_tag_count = len(
            source.slaves["s_src_1"].tag_types["alpha"].tags
        )

        _ = deep_copy_master(source)

        self.assertEqual(source.name, src_name)
        self.assertEqual(len(source.slaves), src_slave_count)
        self.assertEqual(
            len(source.slaves["s_src_1"].tag_types["alpha"].tags),
            src_tag_count,
        )


class BuildDuplicateMasterCompositeTests(unittest.TestCase):
    def test_composite_children_shape_and_shells_are_empty(self):
        state = _build_state_with_one_master()
        source = state.master("m_src")

        composite = build_duplicate_master_composite(
            source=source,
            existing_master_names=[source.name],
            id_factory=_counter_id_factory(),
        )

        # Expected children: 1 AddMaster + 2 AddSlave
        # + (2 tag types + 2+1 tags on s_src_1) + 0 on s_src_2 = 1+2+2+3 = 8.
        self.assertEqual(len(composite.children), 8)

        head = composite.children[0]
        self.assertIsInstance(head, AddMasterCommand)
        self.assertEqual(head.master.slaves, {})
        # AddSlaveCommand entries carry empty tag_types shells.
        slave_cmds = [
            c for c in composite.children
            if isinstance(c, AddSlaveCommand)
        ]
        self.assertEqual(len(slave_cmds), 2)
        for sc in slave_cmds:
            self.assertEqual(sc.slave.tag_types, {})
        # AddTagTypeCommand entries carry empty tags list.
        tt_cmds = [
            c for c in composite.children
            if isinstance(c, AddTagTypeCommand)
        ]
        self.assertEqual(len(tt_cmds), 2)
        for ttc in tt_cmds:
            self.assertEqual(ttc.tag_type.tags, [])
        # Three AddTagCommands for the three source tags.
        tag_cmds = [
            c for c in composite.children
            if isinstance(c, AddTagCommand)
        ]
        self.assertEqual(len(tag_cmds), 3)

    def test_new_master_id_and_name_from_factory_and_resolver(self):
        state = _build_state_with_one_master()
        source = state.master("m_src")

        composite = build_duplicate_master_composite(
            source=source,
            existing_master_names=["Stage"],
            id_factory=_counter_id_factory(),
        )

        head = composite.children[0]
        self.assertIsInstance(head, AddMasterCommand)
        self.assertEqual(head.master.id, "id000001")
        self.assertEqual(head.master.name, "Stage (copy)")

    def test_execute_duplicates_full_subtree_into_state(self):
        state = _build_state_with_one_master()
        source = state.master("m_src")

        composite = build_duplicate_master_composite(
            source=source,
            existing_master_names=[m.name for m in state.masters().values()],
            id_factory=_counter_id_factory(),
        )
        stack = CommandStack(state)
        stack.push(composite)

        self.assertIn("id000001", state.masters())
        new_master = state.master("id000001")
        self.assertEqual(new_master.name, "Stage (copy)")
        self.assertEqual(len(new_master.slaves), 2)
        s1 = new_master.slaves["id000002"]
        self.assertEqual(s1.name, "Left")
        self.assertEqual(s1.pin, "0")
        self.assertEqual(s1.led_count, 30)
        self.assertEqual(set(s1.tag_types), {"alpha", "beta"})
        alpha = s1.tag_types["alpha"]
        self.assertEqual(alpha.color, [10, 20, 30])
        self.assertEqual(alpha.topology, [0, 1])
        self.assertEqual([t.time_seconds for t in alpha.tags], [0.5, 1.5])
        beta = s1.tag_types["beta"]
        self.assertEqual([t.time_seconds for t in beta.tags], [2.0])

    def test_undo_removes_entire_duplicated_subtree(self):
        state = _build_state_with_one_master()
        source = state.master("m_src")
        masters_before = dict(state.masters())
        tags_before = list(
            state.master("m_src").slaves["s_src_1"].tag_types["alpha"].tags
        )

        composite = build_duplicate_master_composite(
            source=source,
            existing_master_names=[m.name for m in state.masters().values()],
            id_factory=_counter_id_factory(),
        )
        stack = CommandStack(state)
        stack.push(composite)
        self.assertIn("id000001", state.masters())

        stack.undo()

        self.assertNotIn("id000001", state.masters())
        self.assertEqual(set(state.masters()), set(masters_before))
        # Source subtree untouched.
        self.assertEqual(
            list(
                state.master("m_src").slaves["s_src_1"]
                .tag_types["alpha"].tags
            ),
            tags_before,
        )

    def test_duplicated_subtree_shares_no_refs_with_source(self):
        state = _build_state_with_one_master()
        source = state.master("m_src")
        composite = build_duplicate_master_composite(
            source=source,
            existing_master_names=[source.name],
            id_factory=_counter_id_factory(),
        )
        stack = CommandStack(state)
        stack.push(composite)

        dup_master = state.master("id000001")
        src_alpha_tags = source.slaves["s_src_1"].tag_types["alpha"].tags
        dup_alpha_tags = (
            dup_master.slaves["id000002"].tag_types["alpha"].tags
        )
        self.assertEqual(len(src_alpha_tags), len(dup_alpha_tags))
        for src_tag, dup_tag in zip(src_alpha_tags, dup_alpha_tags):
            self.assertIsNot(src_tag, dup_tag)
            self.assertEqual(src_tag.time_seconds, dup_tag.time_seconds)
            self.assertEqual(src_tag.action, dup_tag.action)
            self.assertEqual(src_tag.colors, dup_tag.colors)

    def test_name_collides_with_existing_copy_produces_copy_2(self):
        state = _build_state_with_one_master()
        source = state.master("m_src")
        composite = build_duplicate_master_composite(
            source=source,
            existing_master_names=["Stage", "Stage (copy)"],
            id_factory=_counter_id_factory(),
        )
        head = composite.children[0]
        self.assertEqual(head.master.name, "Stage (copy 2)")


class BuildDuplicateSlaveCompositeTests(unittest.TestCase):
    def test_composite_children_shape(self):
        state = _build_state_with_one_master()
        source = state.master("m_src").slaves["s_src_1"]

        composite = build_duplicate_slave_composite(
            source=source,
            target_master_id="m_src",
            existing_slave_names=[
                s.name for s in state.master("m_src").slaves.values()
            ],
            id_factory=_counter_id_factory(),
        )

        # 1 AddSlave + 2 AddTagType + 3 AddTag = 6.
        self.assertEqual(len(composite.children), 6)
        self.assertIsInstance(composite.children[0], AddSlaveCommand)
        self.assertEqual(composite.children[0].slave.tag_types, {})
        self.assertEqual(composite.children[0].master_id, "m_src")

    def test_execute_duplicates_slave_with_subtree(self):
        state = _build_state_with_one_master()
        source = state.master("m_src").slaves["s_src_1"]

        composite = build_duplicate_slave_composite(
            source=source,
            target_master_id="m_src",
            existing_slave_names=[
                s.name for s in state.master("m_src").slaves.values()
            ],
            id_factory=_counter_id_factory(),
        )
        stack = CommandStack(state)
        stack.push(composite)

        master = state.master("m_src")
        self.assertIn("id000001", master.slaves)
        dup = master.slaves["id000001"]
        self.assertEqual(dup.name, "Left (copy)")
        self.assertEqual(dup.pin, "0")
        self.assertEqual(dup.led_count, 30)
        self.assertEqual(set(dup.tag_types), {"alpha", "beta"})
        self.assertEqual(
            [t.time_seconds for t in dup.tag_types["alpha"].tags],
            [0.5, 1.5],
        )
        self.assertEqual(
            [t.time_seconds for t in dup.tag_types["beta"].tags],
            [2.0],
        )

    def test_undo_removes_duplicated_slave_and_subtree(self):
        state = _build_state_with_one_master()
        source = state.master("m_src").slaves["s_src_1"]
        slaves_before = set(state.master("m_src").slaves)

        composite = build_duplicate_slave_composite(
            source=source,
            target_master_id="m_src",
            existing_slave_names=[
                s.name for s in state.master("m_src").slaves.values()
            ],
            id_factory=_counter_id_factory(),
        )
        stack = CommandStack(state)
        stack.push(composite)
        self.assertIn("id000001", state.master("m_src").slaves)

        stack.undo()

        self.assertEqual(
            set(state.master("m_src").slaves), slaves_before,
        )
        # Source still has its tags.
        self.assertEqual(
            [
                t.time_seconds for t in
                state.master("m_src").slaves["s_src_1"]
                .tag_types["alpha"].tags
            ],
            [0.5, 1.5],
        )

    def test_new_slave_id_and_name_respect_factory_and_resolver(self):
        state = _build_state_with_one_master()
        source = state.master("m_src").slaves["s_src_1"]

        composite = build_duplicate_slave_composite(
            source=source,
            target_master_id="m_src",
            existing_slave_names=["Left", "Left (copy)", "Right"],
            id_factory=_counter_id_factory(),
        )

        head = composite.children[0]
        self.assertIsInstance(head, AddSlaveCommand)
        self.assertEqual(head.slave.id, "id000001")
        self.assertEqual(head.slave.name, "Left (copy 2)")

    def test_duplicated_slave_shares_no_tag_refs_with_source(self):
        state = _build_state_with_one_master()
        source = state.master("m_src").slaves["s_src_1"]
        composite = build_duplicate_slave_composite(
            source=source,
            target_master_id="m_src",
            existing_slave_names=[
                s.name for s in state.master("m_src").slaves.values()
            ],
            id_factory=_counter_id_factory(),
        )
        stack = CommandStack(state)
        stack.push(composite)

        src_alpha = source.tag_types["alpha"].tags
        dup_alpha = (
            state.master("m_src").slaves["id000001"]
            .tag_types["alpha"].tags
        )
        for src_tag, dup_tag in zip(src_alpha, dup_alpha):
            self.assertIsNot(src_tag, dup_tag)


if __name__ == "__main__":
    unittest.main()
