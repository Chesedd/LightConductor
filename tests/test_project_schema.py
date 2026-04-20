import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.infrastructure.project_schema import (
    CURRENT_SCHEMA_VERSION,
    SchemaValidationError,
    load_and_migrate,
    migrate_to_current,
    unwrap_boxes,
    validate,
    wrap_boxes,
)


def _minimal_tag():
    return {"time": 1.5, "action": True, "colors": []}


def _minimal_tag_type(tags=None):
    return {
        "color": [0, 0, 0],
        "pin": "3",
        "segment_start": 0,
        "segment_size": 4,
        "row": 1,
        "table": 1,
        "topology": [0, 1, 2, 3],
        "tags": tags if tags is not None else {},
    }


def _minimal_slave(tag_types=None):
    return {
        "name": "S",
        "pin": "5",
        "led_count": 30,
        "grid_rows": 1,
        "grid_columns": 30,
        "led_cells": list(range(30)),
        "id": "s1",
        "tagTypes": tag_types if tag_types is not None else {},
    }


def _minimal_master(slaves=None):
    return {
        "name": "M",
        "id": "m1",
        "ip": "192.168.0.1",
        "slaves": slaves if slaves is not None else {},
    }


class MigrationTests(unittest.TestCase):
    def test_migrate_wraps_legacy_empty_dict(self):
        result = migrate_to_current({})
        self.assertEqual(
            result, {"schema_version": CURRENT_SCHEMA_VERSION, "masters": {}}
        )

    def test_migrate_wraps_legacy_non_empty_dict(self):
        legacy = {"m1": _minimal_master()}
        result = migrate_to_current(legacy)
        self.assertEqual(result["schema_version"], CURRENT_SCHEMA_VERSION)
        self.assertEqual(result["masters"], legacy)

    def test_migrate_passthrough_current_version(self):
        envelope = wrap_boxes({})
        self.assertEqual(migrate_to_current(envelope), envelope)

    def test_migrate_rejects_future_version(self):
        with self.assertRaises(SchemaValidationError):
            migrate_to_current({"schema_version": 999, "masters": {}})

    def test_migrate_rejects_non_dict(self):
        with self.assertRaises(SchemaValidationError):
            migrate_to_current([])

    def test_migrate_coerces_legacy_string_tag_actions(self):
        legacy_on = {"time": 1.0, "action": "On", "colors": []}
        legacy_off = {"time": 2.0, "action": "Off", "colors": []}
        tag_type = _minimal_tag_type(tags={"0": legacy_on, "1": legacy_off})
        slave = _minimal_slave(tag_types={"front": tag_type})
        master = _minimal_master(slaves={"s1": slave})
        legacy = {"m1": master}

        result = migrate_to_current(legacy)

        coerced_tags = result["masters"]["m1"]["slaves"]["s1"]["tagTypes"]["front"][
            "tags"
        ]
        self.assertIs(coerced_tags["0"]["action"], True)
        self.assertIs(coerced_tags["1"]["action"], False)
        validate(result)

    def test_migrate_v1_to_current_fills_grid_fields(self):
        # Hand-crafted v1 envelope: schema_version=1, two slaves each
        # lacking grid_rows/grid_columns. Migration must bump schema
        # to current (v3) and populate grid fields from led_count.
        envelope = {
            "schema_version": 1,
            "masters": {
                "m1": {
                    "name": "M",
                    "id": "m1",
                    "ip": "10.0.0.1",
                    "slaves": {
                        "s1": {
                            "name": "S1",
                            "pin": "1",
                            "led_count": 30,
                            "id": "s1",
                            "tagTypes": {},
                        },
                        "s2": {
                            "name": "S2",
                            "pin": "2",
                            "led_count": 60,
                            "id": "s2",
                            "tagTypes": {},
                        },
                    },
                }
            },
        }

        result = migrate_to_current(envelope)

        self.assertEqual(result["schema_version"], CURRENT_SCHEMA_VERSION)
        slaves = result["masters"]["m1"]["slaves"]
        self.assertEqual(slaves["s1"]["grid_rows"], 1)
        self.assertEqual(slaves["s1"]["grid_columns"], 30)
        self.assertEqual(slaves["s2"]["grid_rows"], 1)
        self.assertEqual(slaves["s2"]["grid_columns"], 60)
        validate(result)

    def test_migrate_v0_legacy_goes_to_current_via_v1_v2(self):
        # Legacy dict without schema_version (pre-v1 project). Chain:
        # v0 → v1 (wrap_boxes) → v2 (grid fields) → v3 (led_cells).
        legacy = {
            "m1": {
                "name": "M",
                "id": "m1",
                "ip": "10.0.0.1",
                "slaves": {
                    "s1": {
                        "name": "S1",
                        "pin": "1",
                        "led_count": 45,
                        "id": "s1",
                        "tagTypes": {},
                    },
                },
            }
        }

        result = migrate_to_current(legacy)

        self.assertEqual(result["schema_version"], CURRENT_SCHEMA_VERSION)
        slave = result["masters"]["m1"]["slaves"]["s1"]
        self.assertEqual(slave["grid_rows"], 1)
        self.assertEqual(slave["grid_columns"], 45)
        validate(result)

    def test_migrate_v2_to_v3_fills_led_cells(self):
        # Hand-crafted v2 envelope: schema_version=2, two slaves
        # each lacking led_cells. Migration must bump to v3 and
        # populate led_cells as [0..led_count-1].
        envelope = {
            "schema_version": 2,
            "masters": {
                "m1": {
                    "name": "M",
                    "id": "m1",
                    "ip": "10.0.0.1",
                    "slaves": {
                        "s1": {
                            "name": "S1",
                            "pin": "1",
                            "led_count": 4,
                            "grid_rows": 2,
                            "grid_columns": 2,
                            "id": "s1",
                            "tagTypes": {},
                        },
                        "s2": {
                            "name": "S2",
                            "pin": "2",
                            "led_count": 0,
                            "grid_rows": 1,
                            "grid_columns": 1,
                            "id": "s2",
                            "tagTypes": {},
                        },
                    },
                }
            },
        }

        result = migrate_to_current(envelope)

        self.assertEqual(result["schema_version"], 3)
        slaves = result["masters"]["m1"]["slaves"]
        self.assertEqual(slaves["s1"]["led_cells"], [0, 1, 2, 3])
        self.assertEqual(slaves["s2"]["led_cells"], [])
        validate(result)

    def test_migrate_legacy_v0_goes_to_v3(self):
        # v0 legacy dict (no schema_version) must chain through
        # v1 → v2 → v3 and arrive with led_cells populated.
        legacy = {
            "m1": {
                "name": "M",
                "id": "m1",
                "ip": "10.0.0.1",
                "slaves": {
                    "s1": {
                        "name": "S1",
                        "pin": "1",
                        "led_count": 6,
                        "id": "s1",
                        "tagTypes": {},
                    },
                },
            }
        }

        result = migrate_to_current(legacy)

        self.assertEqual(result["schema_version"], 3)
        slave = result["masters"]["m1"]["slaves"]["s1"]
        self.assertEqual(slave["led_cells"], [0, 1, 2, 3, 4, 5])
        validate(result)

    def test_migrate_v3_envelope_passes_through_unchanged(self):
        # A v3 envelope with non-sequential led_cells must be
        # preserved verbatim by migrate_to_current.
        envelope = {
            "schema_version": 3,
            "masters": {
                "m1": {
                    "name": "M",
                    "id": "m1",
                    "ip": "10.0.0.1",
                    "slaves": {
                        "s1": {
                            "name": "S1",
                            "pin": "1",
                            "led_count": 4,
                            "grid_rows": 2,
                            "grid_columns": 2,
                            "led_cells": [3, 1, 0, 2],
                            "id": "s1",
                            "tagTypes": {},
                        }
                    },
                }
            },
        }

        result = migrate_to_current(envelope)

        slave = result["masters"]["m1"]["slaves"]["s1"]
        self.assertEqual(slave["led_cells"], [3, 1, 0, 2])
        self.assertEqual(result["schema_version"], 3)


class WrapUnwrapTests(unittest.TestCase):
    def test_wrap_unwrap_roundtrip(self):
        boxes = {"a": _minimal_master()}
        self.assertEqual(unwrap_boxes(wrap_boxes(boxes)), boxes)


class ValidateHappyPathTests(unittest.TestCase):
    def test_validate_accepts_empty_envelope(self):
        validate({"schema_version": CURRENT_SCHEMA_VERSION, "masters": {}})

    def test_validate_accepts_realistic_structure(self):
        envelope = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "masters": {
                "m1": _minimal_master(
                    slaves={
                        "s1": _minimal_slave(
                            tag_types={
                                "front": _minimal_tag_type(tags={"0": _minimal_tag()})
                            }
                        )
                    }
                )
            },
        }
        validate(envelope)

    def test_validate_allows_extra_keys(self):
        envelope = wrap_boxes({})
        envelope["future_field"] = "ok"
        validate(envelope)

    def test_validate_accepts_int_pin_and_string_pin(self):
        slaves = {
            "s1": _minimal_slave(),
            "s2": {**_minimal_slave(), "pin": 7},
        }
        envelope = wrap_boxes({"m1": _minimal_master(slaves=slaves)})
        validate(envelope)


class ValidateRejectionTests(unittest.TestCase):
    def test_validate_rejects_missing_schema_version(self):
        with self.assertRaises(SchemaValidationError) as ctx:
            validate({"masters": {}})
        self.assertIn("schema_version", str(ctx.exception))

    def test_validate_rejects_wrong_schema_version(self):
        with self.assertRaises(SchemaValidationError) as ctx:
            validate({"schema_version": 1, "masters": {}})
        self.assertIn("1", str(ctx.exception))

    def test_validate_rejects_missing_masters(self):
        with self.assertRaises(SchemaValidationError) as ctx:
            validate({"schema_version": CURRENT_SCHEMA_VERSION})
        self.assertIn("masters", str(ctx.exception))

    def test_validate_rejects_slave_missing_required_field(self):
        slave = _minimal_slave()
        del slave["pin"]
        envelope = wrap_boxes({"m1": _minimal_master(slaves={"s1": slave})})
        with self.assertRaises(SchemaValidationError) as ctx:
            validate(envelope)
        msg = str(ctx.exception)
        self.assertIn("masters.m1.slaves.s1", msg)
        self.assertIn("pin", msg)

    def test_validate_rejects_tag_wrong_type(self):
        tag = _minimal_tag()
        tag["time"] = "oops"
        tag_type = _minimal_tag_type(tags={"0": tag})
        slave = _minimal_slave(tag_types={"front": tag_type})
        envelope = wrap_boxes({"m1": _minimal_master(slaves={"s1": slave})})
        with self.assertRaises(SchemaValidationError) as ctx:
            validate(envelope)
        msg = str(ctx.exception)
        self.assertIn("masters.m1.slaves.s1.tagTypes.front.tags.0", msg)
        self.assertIn("time", msg)

    def test_validate_rejects_master_with_wrong_ip_type(self):
        master = _minimal_master()
        master["ip"] = 12345
        envelope = wrap_boxes({"m1": master})
        with self.assertRaises(SchemaValidationError) as ctx:
            validate(envelope)
        self.assertIn("masters.m1.ip", str(ctx.exception))


class FileIOTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, payload):
        path = self.tmp_dir / name
        path.write_text(payload, encoding="utf-8")
        return path

    def test_load_and_migrate_legacy_file(self):
        legacy = {"m1": _minimal_master()}
        path = self._write("legacy.json", json.dumps(legacy))
        envelope = load_and_migrate(path)
        self.assertEqual(envelope["schema_version"], CURRENT_SCHEMA_VERSION)
        self.assertEqual(envelope["masters"], legacy)

    def test_load_and_migrate_current_file(self):
        envelope = wrap_boxes({"m1": _minimal_master()})
        path = self._write("current.json", json.dumps(envelope))
        self.assertEqual(load_and_migrate(path), envelope)

    def test_load_and_migrate_corrupt_file(self):
        path = self._write("broken.json", "{")
        with self.assertRaises(SchemaValidationError) as ctx:
            load_and_migrate(path)
        self.assertIsInstance(ctx.exception.__cause__, json.JSONDecodeError)


if __name__ == "__main__":
    unittest.main()
