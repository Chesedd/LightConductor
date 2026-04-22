import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.application.project_state import (
    DuplicateSlavePinError,
    MasterAdded,
    MasterRemoved,
    MasterUpdated,
    ProjectState,
    SlaveAdded,
    SlaveRemoved,
    StateReplaced,
    TagAdded,
    TagRemoved,
    TagTypeAdded,
    TagTypeRemoved,
    TagTypeUpdated,
    TagUpdated,
)
from lightconductor.domain.models import Master, Slave, Tag, TagType


@pytest.fixture
def state():
    return ProjectState()


def _capture(state):
    events = []
    state.subscribe(lambda ev: events.append(ev))
    return events


def _master(master_id="m1", name="Master 1"):
    return Master(id=master_id, name=name)


def _slave(slave_id="s1", name="Slave 1", pin="0"):
    return Slave(id=slave_id, name=name, pin=pin)


def _tag_type(name="tt1", pin="1", rows=1, columns=1):
    return TagType(name=name, pin=pin, rows=rows, columns=columns)


def _tag(time_seconds=0.0, action=True, colors=None):
    return Tag(
        time_seconds=time_seconds,
        action=action,
        colors=list(colors) if colors is not None else [],
    )


def _seed_tag(state, *, tag=None):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1"))
    state.add_tag_type("m1", "s1", _tag_type("tt1"))
    state.add_tag("m1", "s1", "tt1", tag or _tag())


# ---------------------------------------------------------------------------
# Basic state + master ops
# ---------------------------------------------------------------------------


def test_new_state_has_no_masters(state):
    assert state.masters() == {}
    assert state.has_master("x") is False


def test_add_master_appears_in_queries_and_emits_master_added(state):
    events = _capture(state)
    m = _master("m1")

    state.add_master(m)

    assert state.has_master("m1") is True
    assert state.master("m1") is m
    assert len(events) == 1
    assert isinstance(events[0], MasterAdded)
    assert events[0].master_id == "m1"


def test_add_master_duplicate_raises_value_error(state):
    state.add_master(_master("m1"))
    events = _capture(state)

    with pytest.raises(ValueError):
        state.add_master(_master("m1", name="dup"))

    assert events == []


def test_remove_master_missing_raises_key_error(state):
    events = _capture(state)

    with pytest.raises(KeyError):
        state.remove_master("nope")

    assert events == []


def test_remove_master_emits_master_removed(state):
    state.add_master(_master("m1"))
    events = _capture(state)

    state.remove_master("m1")

    assert state.has_master("m1") is False
    assert len(events) == 1
    assert isinstance(events[0], MasterRemoved)
    assert events[0].master_id == "m1"


def test_update_master_ip_mutates_ip_and_emits_master_updated(state):
    master = _master("m1")
    master.ip = "10.0.0.1"
    state.add_master(master)
    events = _capture(state)

    state.update_master_ip("m1", "10.0.0.99")

    assert state.master("m1").ip == "10.0.0.99"
    assert len(events) == 1
    assert isinstance(events[0], MasterUpdated)
    assert events[0].master_id == "m1"


def test_update_master_ip_missing_master_raises_key_error(state):
    events = _capture(state)

    with pytest.raises(KeyError):
        state.update_master_ip("nope", "10.0.0.1")

    assert events == []


def test_update_master_ip_same_value_still_emits_master_updated(state):
    master = _master("m1")
    master.ip = "10.0.0.1"
    state.add_master(master)
    events = _capture(state)

    state.update_master_ip("m1", "10.0.0.1")

    assert state.master("m1").ip == "10.0.0.1"
    assert len(events) == 1
    assert isinstance(events[0], MasterUpdated)
    assert events[0].master_id == "m1"


# ---------------------------------------------------------------------------
# Slave ops
# ---------------------------------------------------------------------------


def test_add_slave_to_missing_master_raises_key_error(state):
    events = _capture(state)

    with pytest.raises(KeyError):
        state.add_slave("nope", _slave("s1"))

    assert events == []


def test_add_slave_emits_slave_added_and_attaches(state):
    state.add_master(_master("m1"))
    events = _capture(state)
    slave = _slave("s1")

    state.add_slave("m1", slave)

    assert state.master("m1").slaves["s1"] is slave
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, SlaveAdded)
    assert ev.master_id == "m1"
    assert ev.slave_id == "s1"


def test_add_slave_duplicate_id_raises_value_error(state):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1"))
    events = _capture(state)

    with pytest.raises(ValueError):
        state.add_slave("m1", _slave("s1", name="dup"))

    assert events == []


def test_add_slave_duplicate_pin_raises_duplicate_slave_pin_error(state):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1", pin="7"))

    with pytest.raises(DuplicateSlavePinError) as excinfo:
        state.add_slave("m1", _slave("s2", name="dup-pin", pin="7"))

    err = excinfo.value
    assert err.master_id == "m1"
    assert err.pin == "7"
    assert err.existing_slave_id == "s1"
    assert err.new_slave_id == "s2"
    assert isinstance(err, ValueError)
    assert "s2" not in state.master("m1").slaves


def test_add_slave_duplicate_pin_does_not_emit_slave_added(state):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1", pin="7"))
    events = _capture(state)

    with pytest.raises(DuplicateSlavePinError):
        state.add_slave("m1", _slave("s2", pin="7"))

    assert [ev for ev in events if isinstance(ev, SlaveAdded)] == []


def test_add_slave_same_pin_across_different_masters_succeeds(state):
    state.add_master(_master("m1"))
    state.add_master(_master("m2", name="Master 2"))
    state.add_slave("m1", _slave("s1", pin="7"))

    state.add_slave("m2", _slave("s2", pin="7"))

    assert "s1" in state.master("m1").slaves
    assert "s2" in state.master("m2").slaves


def test_remove_slave_missing_raises_key_error(state):
    state.add_master(_master("m1"))
    events = _capture(state)

    with pytest.raises(KeyError):
        state.remove_slave("m1", "missing")

    assert events == []


def test_remove_slave_emits_slave_removed(state):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1"))
    events = _capture(state)

    state.remove_slave("m1", "s1")

    assert "s1" not in state.master("m1").slaves
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, SlaveRemoved)
    assert ev.master_id == "m1"
    assert ev.slave_id == "s1"


# ---------------------------------------------------------------------------
# TagType ops
# ---------------------------------------------------------------------------


def test_add_tag_type_and_remove_emit_paired_events(state):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1"))
    events = _capture(state)
    tt = _tag_type("tt1")

    state.add_tag_type("m1", "s1", tt)
    state.remove_tag_type("m1", "s1", "tt1")

    assert len(events) == 2
    added, removed = events
    assert isinstance(added, TagTypeAdded)
    assert (added.master_id, added.slave_id, added.type_name) == ("m1", "s1", "tt1")
    assert isinstance(removed, TagTypeRemoved)
    assert (removed.master_id, removed.slave_id, removed.type_name) == (
        "m1",
        "s1",
        "tt1",
    )
    assert "tt1" not in state.master("m1").slaves["s1"].tag_types


def test_add_tag_type_duplicate_raises_value_error(state):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1"))
    state.add_tag_type("m1", "s1", _tag_type("tt1"))
    events = _capture(state)

    with pytest.raises(ValueError):
        state.add_tag_type("m1", "s1", _tag_type("tt1"))

    assert events == []


def test_remove_tag_type_missing_raises_key_error(state):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1"))
    events = _capture(state)

    with pytest.raises(KeyError):
        state.remove_tag_type("m1", "s1", "nope")

    assert events == []


def test_update_tag_type_mutates_and_emits_tag_type_updated(state):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1"))
    state.add_tag_type("m1", "s1", _tag_type("tt1", pin="1"))
    events = _capture(state)

    state.update_tag_type("m1", "s1", "tt1", pin="42", color=[1, 2, 3])

    tag_type = state.master("m1").slaves["s1"].tag_types["tt1"]
    assert tag_type.pin == "42"
    assert tag_type.color == [1, 2, 3]
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, TagTypeUpdated)
    assert (ev.master_id, ev.slave_id, ev.type_name) == ("m1", "s1", "tt1")

    # Second call with no-op args still emits and leaves fields unchanged.
    state.update_tag_type("m1", "s1", "tt1", pin=None, color=None)

    assert tag_type.pin == "42"
    assert tag_type.color == [1, 2, 3]
    assert len(events) == 2
    assert isinstance(events[1], TagTypeUpdated)
    assert (events[1].master_id, events[1].slave_id, events[1].type_name) == (
        "m1",
        "s1",
        "tt1",
    )


# ---------------------------------------------------------------------------
# Tag ops
# ---------------------------------------------------------------------------


def test_add_tag_returns_new_index_and_emits_tag_added(state):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1"))
    state.add_tag_type("m1", "s1", _tag_type("tt1"))
    events = _capture(state)

    idx0 = state.add_tag("m1", "s1", "tt1", _tag(time_seconds=0.0))
    idx1 = state.add_tag("m1", "s1", "tt1", _tag(time_seconds=1.0))

    assert idx0 == 0
    assert idx1 == 1
    assert len(events) == 2
    for ev, expected_idx in zip(events, (0, 1), strict=True):
        assert isinstance(ev, TagAdded)
        assert ev.master_id == "m1"
        assert ev.slave_id == "s1"
        assert ev.type_name == "tt1"
        assert ev.tag_index == expected_idx


def test_remove_tag_shifts_indices(state):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1"))
    state.add_tag_type("m1", "s1", _tag_type("tt1"))
    t0 = _tag(time_seconds=0.0)
    t1 = _tag(time_seconds=1.0)
    t2 = _tag(time_seconds=2.0)
    state.add_tag("m1", "s1", "tt1", t0)
    state.add_tag("m1", "s1", "tt1", t1)
    state.add_tag("m1", "s1", "tt1", t2)
    events = _capture(state)

    state.remove_tag("m1", "s1", "tt1", 0)

    remaining = state.master("m1").slaves["s1"].tag_types["tt1"].tags
    assert len(remaining) == 2
    assert remaining[0] is t1
    assert remaining[1] is t2
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, TagRemoved)
    assert ev.tag_index == 0


def test_remove_tag_out_of_range_raises_index_error(state):
    _seed_tag(state)
    events = _capture(state)

    with pytest.raises(IndexError):
        state.remove_tag("m1", "s1", "tt1", 5)

    assert events == []


def test_update_tag_partial_fields(state):
    seeded = _tag(time_seconds=1.0, action=True, colors=[[1, 2, 3]])
    _seed_tag(state, tag=seeded)
    events = _capture(state)

    state.update_tag("m1", "s1", "tt1", 0, colors=[[9, 9, 9]])

    tag = state.master("m1").slaves["s1"].tag_types["tt1"].tags[0]
    assert tag.time_seconds == 1.0
    assert tag.action is True
    assert tag.colors == [[9, 9, 9]]
    assert len(events) == 1
    assert isinstance(events[0], TagUpdated)
    assert events[0].tag_index == 0


def test_update_tag_with_all_none_still_emits(state):
    seeded = _tag(time_seconds=2.5, action=False, colors=[[5, 5, 5]])
    _seed_tag(state, tag=seeded)
    events = _capture(state)

    state.update_tag("m1", "s1", "tt1", 0)

    tag = state.master("m1").slaves["s1"].tag_types["tt1"].tags[0]
    assert tag.time_seconds == 2.5
    assert tag.action is False
    assert tag.colors == [[5, 5, 5]]
    assert len(events) == 1
    assert isinstance(events[0], TagUpdated)


def test_add_tag_bisect_inserts_by_time_seconds(state):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1"))
    state.add_tag_type("m1", "s1", _tag_type("tt1"))

    idx_a = state.add_tag("m1", "s1", "tt1", _tag(time_seconds=2.0))
    idx_b = state.add_tag("m1", "s1", "tt1", _tag(time_seconds=0.5))
    idx_c = state.add_tag("m1", "s1", "tt1", _tag(time_seconds=1.5))
    idx_d = state.add_tag("m1", "s1", "tt1", _tag(time_seconds=1.5))

    # bisect_left returns the leftmost index for equal values, so the
    # second 1.5 is inserted at index 1 (pushing the first 1.5 to
    # index 2).
    assert idx_a == 0
    assert idx_b == 0
    assert idx_c == 1
    assert idx_d == 1

    tags = state.master("m1").slaves["s1"].tag_types["tt1"].tags
    assert [t.time_seconds for t in tags] == [0.5, 1.5, 1.5, 2.0]


def test_update_tag_time_change_repositions(state):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1"))
    state.add_tag_type("m1", "s1", _tag_type("tt1"))
    state.add_tag("m1", "s1", "tt1", _tag(time_seconds=0.0))
    state.add_tag("m1", "s1", "tt1", _tag(time_seconds=1.0))
    state.add_tag("m1", "s1", "tt1", _tag(time_seconds=2.0))
    events = _capture(state)

    state.update_tag("m1", "s1", "tt1", 0, time_seconds=1.5)

    tags = state.master("m1").slaves["s1"].tag_types["tt1"].tags
    assert [t.time_seconds for t in tags] == [1.0, 1.5, 2.0]
    assert len(events) == 1
    assert isinstance(events[0], TagUpdated)
    assert events[0].tag_index == 1


def test_update_tag_without_time_change_keeps_index(state):
    state.add_master(_master("m1"))
    state.add_slave("m1", _slave("s1"))
    state.add_tag_type("m1", "s1", _tag_type("tt1"))
    t0 = _tag(time_seconds=0.0, colors=[[1, 1, 1]])
    t1 = _tag(time_seconds=1.0, colors=[[2, 2, 2]])
    state.add_tag("m1", "s1", "tt1", t0)
    state.add_tag("m1", "s1", "tt1", t1)
    events = _capture(state)

    state.update_tag("m1", "s1", "tt1", 0, colors=[[9, 9, 9]])

    tags = state.master("m1").slaves["s1"].tag_types["tt1"].tags
    assert tags[0] is t0
    assert tags[0].colors == [[9, 9, 9]]
    assert len(events) == 1
    assert isinstance(events[0], TagUpdated)
    assert events[0].tag_index == 0


def test_load_masters_sorts_tags_by_time(state):
    master = _master("m1")
    slave = _slave("s1")
    tag_type = _tag_type("tt1")
    tag_type.tags = [
        _tag(time_seconds=3.0),
        _tag(time_seconds=1.0),
        _tag(time_seconds=2.0),
    ]
    slave.tag_types[tag_type.name] = tag_type
    master.slaves[slave.id] = slave

    state.load_masters({"m1": master})

    tags = state.master("m1").slaves["s1"].tag_types["tt1"].tags
    assert [t.time_seconds for t in tags] == [1.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# Subscription behaviors
# ---------------------------------------------------------------------------


def test_subscribe_returns_working_unsubscribe(state):
    events = []
    unsubscribe = state.subscribe(lambda ev: events.append(ev))

    state.add_master(_master("m1"))
    assert len(events) == 1

    unsubscribe()
    state.add_master(_master("m2"))
    assert len(events) == 1


def test_unsubscribe_is_idempotent(state):
    unsubscribe = state.subscribe(lambda ev: None)
    unsubscribe()
    unsubscribe()  # must not raise


def test_listener_exception_does_not_block_others(state):
    received_second = []

    def first(ev):
        raise RuntimeError("boom")

    def second(ev):
        received_second.append(ev)

    state.subscribe(first)
    state.subscribe(second)

    state.add_master(_master("m1"))

    assert len(received_second) == 1
    assert isinstance(received_second[0], MasterAdded)


# ---------------------------------------------------------------------------
# Bulk load + query-copy semantics
# ---------------------------------------------------------------------------


def test_load_masters_emits_state_replaced_once(state):
    events = _capture(state)
    payload = {"m1": _master("m1"), "m2": _master("m2")}

    state.load_masters(payload)

    assert len(events) == 1
    assert isinstance(events[0], StateReplaced)
    loaded = state.masters()
    assert set(loaded.keys()) == {"m1", "m2"}


def test_load_masters_stores_shallow_copy(state):
    payload = {"m1": _master("m1")}
    state.load_masters(payload)

    payload["m2"] = _master("m2")
    payload.pop("m1")

    assert state.has_master("m1") is True
    assert state.has_master("m2") is False


def test_queries_return_shallow_copies(state):
    state.add_master(_master("m1"))

    snapshot = state.masters()
    snapshot["m2"] = _master("m2")

    assert state.has_master("m2") is False
    assert "m2" not in state.masters()
