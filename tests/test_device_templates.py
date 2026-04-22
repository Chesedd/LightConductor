import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.commands import (
    AddSlaveCommand,
    AddTagCommand,
    AddTagTypeCommand,
    CommandStack,
    CompositeCommand,
)
from lightconductor.application.device_templates import (
    _next_free_int_pin,
    build_apply_template_composite,
    slave_from_template,
    template_from_slave,
)
from lightconductor.application.project_state import (
    DuplicateSlavePinError,
    ProjectState,
)
from lightconductor.domain.models import Master, Slave, Tag, TagType


def _counter_id_factory():
    state = {"n": 0}

    def _next():
        state["n"] += 1
        return f"tpl-{state['n']:03d}"

    return _next


def _make_slave_with_tags():
    """Slave with 2 tag_types: 'alpha' has 3 tags, 'beta' has 2."""
    alpha = TagType(
        name="alpha",
        pin="7",
        rows=1,
        columns=3,
        color=[255, 0, 0],
        topology=[0, 1, 2],
        tags=[
            Tag(time_seconds=0.1, action=True, colors=[[1, 2, 3]]),
            Tag(time_seconds=0.5, action=False, colors=[[4, 5, 6]]),
            Tag(time_seconds=1.2, action=True, colors=[[7, 8, 9]]),
        ],
    )
    beta = TagType(
        name="beta",
        pin="9",
        rows=2,
        columns=2,
        color="blue",
        topology=[3, 4, 5, 6],
        tags=[
            Tag(time_seconds=0.2, action=True, colors=[]),
            Tag(time_seconds=0.8, action=False, colors=[]),
        ],
    )
    return Slave(
        id="s-source",
        name="Source Slave",
        pin="0",
        led_count=60,
        tag_types={"alpha": alpha, "beta": beta},
    )


class TemplateFromSlaveTests(unittest.TestCase):
    def test_template_from_slave_strips_tags_from_each_tag_type(self):
        source = _make_slave_with_tags()
        template = template_from_slave(source, "t1")
        tag_types = template["slave_config"]["tagTypes"]
        self.assertEqual(tag_types["alpha"]["tags"], {})
        self.assertEqual(tag_types["beta"]["tags"], {})

    def test_template_from_slave_preserves_topology_pin_color_name(self):
        source = _make_slave_with_tags()
        template = template_from_slave(source, "t1")
        alpha = template["slave_config"]["tagTypes"]["alpha"]
        self.assertEqual(alpha["pin"], "7")
        self.assertEqual(alpha["color"], [255, 0, 0])
        self.assertEqual(alpha["topology"], [0, 1, 2])
        self.assertIn("alpha", template["slave_config"]["tagTypes"])

    def test_template_from_slave_does_not_mutate_source(self):
        source = _make_slave_with_tags()
        before_alpha = len(source.tag_types["alpha"].tags)
        before_beta = len(source.tag_types["beta"].tags)
        _ = template_from_slave(source, "t1")
        self.assertEqual(
            len(source.tag_types["alpha"].tags),
            before_alpha,
        )
        self.assertEqual(
            len(source.tag_types["beta"].tags),
            before_beta,
        )

    def test_template_from_slave_template_id_uses_factory(self):
        source = _make_slave_with_tags()
        factory = _counter_id_factory()
        t1 = template_from_slave(source, "n", template_id_factory=factory)
        t2 = template_from_slave(source, "n", template_id_factory=factory)
        self.assertEqual(t1["template_id"], "tpl-001")
        self.assertEqual(t2["template_id"], "tpl-002")

    def test_template_from_slave_template_name_stored_verbatim(self):
        source = _make_slave_with_tags()
        named = template_from_slave(source, "My Strip Config")
        self.assertEqual(named["template_name"], "My Strip Config")
        empty = template_from_slave(source, "")
        self.assertEqual(empty["template_name"], "")

    def test_template_from_slave_default_version_is_1(self):
        source = _make_slave_with_tags()
        template = template_from_slave(source, "t1")
        self.assertEqual(template["template_version"], 1)


class SlaveFromTemplateTests(unittest.TestCase):
    def test_slave_from_template_creates_slave_with_fresh_id(self):
        source = _make_slave_with_tags()
        template = template_from_slave(source, "t1")
        dup = slave_from_template(template, "new-123")
        self.assertEqual(dup.id, "new-123")

    def test_slave_from_template_has_empty_tags_per_type(self):
        source = _make_slave_with_tags()
        template = template_from_slave(source, "t1")
        dup = slave_from_template(template, "new-id")
        for tt in dup.tag_types.values():
            self.assertEqual(tt.tags, [])

    def test_slave_from_template_name_override(self):
        source = _make_slave_with_tags()
        template = template_from_slave(source, "t1")
        renamed = slave_from_template(
            template,
            "new-id",
            new_slave_name="Renamed",
        )
        self.assertEqual(renamed.name, "Renamed")
        kept = slave_from_template(template, "new-id")
        self.assertEqual(kept.name, source.name)

    def test_slave_from_template_rejects_non_dict_template(self):
        with self.assertRaises(ValueError):
            slave_from_template("not a dict", "id-1")

    def test_template_from_slave_captures_led_cells(self):
        source = Slave(
            id="s-source",
            name="Src",
            pin="0",
            led_count=3,
            grid_rows=2,
            grid_columns=2,
            led_cells=[2, 0, 1],
            tag_types={},
        )
        template = template_from_slave(source, "t1")
        self.assertEqual(
            template["slave_config"]["led_cells"],
            [2, 0, 1],
        )

    def test_slave_from_template_restores_led_cells(self):
        source = Slave(
            id="s-source",
            name="Src",
            pin="0",
            led_count=3,
            grid_rows=2,
            grid_columns=2,
            led_cells=[2, 0, 1],
            tag_types={},
        )
        template = template_from_slave(source, "t1")
        dup = slave_from_template(template, "new-id")
        self.assertEqual(dup.led_cells, [2, 0, 1])


class BuildApplyTemplateCompositeTests(unittest.TestCase):
    def test_apply_template_composite_children_structure(self):
        source = Slave(
            id="s-source",
            name="Src",
            pin="0",
            led_count=60,
            tag_types={
                "a": TagType(
                    name="a",
                    pin="1",
                    rows=1,
                    columns=1,
                    color=[1, 1, 1],
                    topology=[0],
                ),
                "b": TagType(
                    name="b",
                    pin="2",
                    rows=1,
                    columns=1,
                    color=[2, 2, 2],
                    topology=[1],
                ),
                "c": TagType(
                    name="c",
                    pin="3",
                    rows=1,
                    columns=1,
                    color=[3, 3, 3],
                    topology=[2],
                ),
            },
        )
        template = template_from_slave(source, "t-3types")
        composite = build_apply_template_composite(
            template=template,
            target_master_id="M1",
            new_slave_id="s-new",
        )
        self.assertIsInstance(composite, CompositeCommand)
        slave_cmds = [c for c in composite.children if isinstance(c, AddSlaveCommand)]
        tt_cmds = [c for c in composite.children if isinstance(c, AddTagTypeCommand)]
        tag_cmds = [c for c in composite.children if isinstance(c, AddTagCommand)]
        self.assertEqual(len(slave_cmds), 1)
        self.assertEqual(len(tt_cmds), 3)
        self.assertEqual(len(tag_cmds), 0)
        self.assertEqual(len(composite.children), 4)

    def test_apply_template_end_to_end_via_commandstack(self):
        state = ProjectState()
        state.add_master(Master(id="M1", name="StageOnly"))

        source = _make_slave_with_tags()
        template = template_from_slave(source, "tpl-apply")

        composite = build_apply_template_composite(
            template=template,
            target_master_id="M1",
            new_slave_id="s-new",
        )
        stack = CommandStack(state)
        stack.push(composite)

        master = state.master("M1")
        self.assertIn("s-new", master.slaves)
        applied = master.slaves["s-new"]
        self.assertEqual(set(applied.tag_types), {"alpha", "beta"})
        for tt in applied.tag_types.values():
            self.assertEqual(tt.tags, [])

        stack.undo()
        master_after = state.master("M1")
        self.assertNotIn("s-new", master_after.slaves)
        self.assertEqual(master_after.slaves, {})

    def test_apply_template_to_source_master_with_same_pin_rolls_back(self):
        # Save-as-template then apply-to-same-master: the template
        # carries the source slave's pin verbatim, so the composite
        # must raise DuplicateSlavePinError and leave the master's
        # slave count unchanged (no orphan from a half-applied
        # composite).
        state = ProjectState()
        state.add_master(Master(id="M1", name="Stage"))
        source = _make_slave_with_tags()
        state.add_slave("M1", source)
        before_slave_ids = set(state.master("M1").slaves.keys())

        template = template_from_slave(source, "tpl-self-apply")
        composite = build_apply_template_composite(
            template=template,
            target_master_id="M1",
            new_slave_id="s-new",
        )

        with self.assertRaises(DuplicateSlavePinError) as ctx:
            composite.execute(state)

        self.assertEqual(ctx.exception.master_id, "M1")
        self.assertEqual(ctx.exception.pin, str(source.pin))
        self.assertEqual(ctx.exception.existing_slave_id, source.id)
        self.assertEqual(ctx.exception.new_slave_id, "s-new")
        self.assertEqual(
            set(state.master("M1").slaves.keys()),
            before_slave_ids,
        )


class NextFreeIntPinTests(unittest.TestCase):
    def test_empty_input_yields_zero(self):
        self.assertEqual(_next_free_int_pin([]), "0")

    def test_contiguous_from_zero_yields_next(self):
        self.assertEqual(_next_free_int_pin(["0", "1", "2"]), "3")

    def test_fills_lowest_gap(self):
        self.assertEqual(_next_free_int_pin(["1", "3"]), "0")

    def test_non_integer_entry_returns_none(self):
        self.assertIsNone(_next_free_int_pin(["0", "abc"]))

    def test_contiguous_longer_range(self):
        self.assertEqual(
            _next_free_int_pin(["0", "1", "2", "3"]),
            "4",
        )

    def test_duplicates_are_tolerated(self):
        self.assertEqual(_next_free_int_pin(["0", "0", "1"]), "2")


class ApplyTemplatePinReassignmentTests(unittest.TestCase):
    def test_apply_template_reassigns_pin_when_conflict(self):
        state = ProjectState()
        state.add_master(Master(id="M1", name="Stage"))
        source = _make_slave_with_tags()
        state.add_slave("M1", source)

        template = template_from_slave(source, "tpl-reassign")
        target_master = state.master("M1")
        existing_pins = [str(s.pin) for s in target_master.slaves.values()]
        composite = build_apply_template_composite(
            template=template,
            target_master_id="M1",
            new_slave_id="s-new",
            existing_pins=existing_pins,
        )

        stack = CommandStack(state)
        stack.push(composite)

        master = state.master("M1")
        self.assertIn("s-new", master.slaves)
        pins = {s.pin for s in master.slaves.values()}
        self.assertEqual(len(pins), len(master.slaves))
        self.assertNotEqual(master.slaves["s-new"].pin, str(source.pin))
        self.assertEqual(master.slaves["s-new"].pin, "1")

    def test_apply_template_keeps_pin_when_no_conflict(self):
        state = ProjectState()
        state.add_master(Master(id="M1", name="Empty"))
        source = _make_slave_with_tags()

        template = template_from_slave(source, "tpl-keep")
        target_master = state.master("M1")
        existing_pins = [str(s.pin) for s in target_master.slaves.values()]
        composite = build_apply_template_composite(
            template=template,
            target_master_id="M1",
            new_slave_id="s-new",
            existing_pins=existing_pins,
        )

        stack = CommandStack(state)
        stack.push(composite)

        master = state.master("M1")
        self.assertEqual(master.slaves["s-new"].pin, str(source.pin))

    def test_apply_template_non_int_existing_pins_falls_back(self):
        state = ProjectState()
        state.add_master(Master(id="M1", name="Exotic"))
        exotic = Slave(
            id="s-exotic",
            name="Exotic",
            pin="gpio-3",
            led_count=1,
            tag_types={},
        )
        colliding = Slave(
            id="s-collide",
            name="Collide",
            pin="0",
            led_count=1,
            tag_types={},
        )
        state.add_slave("M1", exotic)
        state.add_slave("M1", colliding)
        source = _make_slave_with_tags()  # pin "0"

        template = template_from_slave(source, "tpl-fallback")
        target_master = state.master("M1")
        existing_pins = [str(s.pin) for s in target_master.slaves.values()]
        composite = build_apply_template_composite(
            template=template,
            target_master_id="M1",
            new_slave_id="s-new",
            existing_pins=existing_pins,
        )

        with self.assertRaises(DuplicateSlavePinError):
            composite.execute(state)


if __name__ == "__main__":
    unittest.main()
