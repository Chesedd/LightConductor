import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lightconductor.config import AppSettings, load_settings, save_settings


class LoadSettingsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.settings_file = self.tmp_dir / "settings.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_creates_file_when_missing(self):
        self.assertFalse(self.settings_file.exists())
        result = load_settings(self.settings_file)
        self.assertEqual(result, AppSettings())
        self.assertTrue(self.settings_file.exists())
        data = json.loads(self.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(
            set(data.keys()),
            {
                "default_master_ip",
                "udp_port",
                "udp_chunk_size",
                "autosave_interval_seconds",
                "color_presets",
                "recent_project_ids",
                "device_templates",
            },
        )

    def test_load_reads_existing_file(self):
        self.settings_file.write_text(
            json.dumps(
                {
                    "default_master_ip": "10.0.0.1",
                    "udp_port": 55555,
                    "udp_chunk_size": 1024,
                }
            ),
            encoding="utf-8",
        )
        result = load_settings(self.settings_file)
        self.assertEqual(result.default_master_ip, "10.0.0.1")
        self.assertEqual(result.udp_port, 55555)
        self.assertEqual(result.udp_chunk_size, 1024)

    def test_load_falls_back_on_corrupt_json(self):
        self.settings_file.write_text("{", encoding="utf-8")
        result = load_settings(self.settings_file)
        self.assertEqual(result, AppSettings())
        self.assertEqual(self.settings_file.read_text(encoding="utf-8"), "{")

    def test_load_ignores_unknown_keys_and_bad_types(self):
        self.settings_file.write_text(
            json.dumps(
                {
                    "default_master_ip": "10.0.0.1",
                    "udp_port": "not-int",
                    "udp_chunk_size": 512,
                    "extra_junk": "ignored",
                }
            ),
            encoding="utf-8",
        )
        result = load_settings(self.settings_file)
        self.assertEqual(result.default_master_ip, "10.0.0.1")
        self.assertEqual(result.udp_port, AppSettings().udp_port)
        self.assertEqual(result.udp_chunk_size, 512)

    def test_save_load_roundtrip(self):
        custom = AppSettings(
            default_master_ip="1.2.3.4",
            udp_port=1234,
            udp_chunk_size=128,
        )
        save_settings(custom, self.settings_file)
        loaded = load_settings(self.settings_file)
        self.assertEqual(loaded, custom)

    def test_load_settings_defaults_autosave_interval(self):
        self.settings_file.write_text(
            json.dumps(
                {
                    "default_master_ip": "10.0.0.1",
                    "udp_port": 55555,
                    "udp_chunk_size": 1024,
                }
            ),
            encoding="utf-8",
        )
        result = load_settings(self.settings_file)
        self.assertEqual(
            result.autosave_interval_seconds,
            AppSettings().autosave_interval_seconds,
        )
        self.assertEqual(result.autosave_interval_seconds, 30)

    def test_save_and_load_settings_preserves_autosave_interval(self):
        custom = AppSettings(autosave_interval_seconds=45)
        save_settings(custom, self.settings_file)
        loaded = load_settings(self.settings_file)
        self.assertEqual(loaded.autosave_interval_seconds, 45)
        self.assertEqual(loaded, custom)

    def _write_settings(self, color_presets_value):
        payload = {
            "default_master_ip": "10.0.0.1",
            "udp_port": 55555,
            "udp_chunk_size": 1024,
            "autosave_interval_seconds": 30,
            "color_presets": color_presets_value,
        }
        self.settings_file.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def test_color_presets_defaults_to_empty_list(self):
        self.assertEqual(AppSettings().color_presets, [])

    def test_color_presets_valid_round_trip(self):
        custom = AppSettings(
            color_presets=[[255, 0, 0], [0, 255, 128]],
        )
        save_settings(custom, self.settings_file)
        loaded = load_settings(self.settings_file)
        self.assertEqual(
            loaded.color_presets,
            [[255, 0, 0], [0, 255, 128]],
        )

    def test_color_presets_wrong_outer_type_uses_default(self):
        self._write_settings(42)
        result = load_settings(self.settings_file)
        self.assertEqual(result.color_presets, [])

    def test_color_presets_wrong_inner_type_uses_default(self):
        self._write_settings([[255, 0, 0], "not a triplet"])
        result = load_settings(self.settings_file)
        self.assertEqual(result.color_presets, [])

    def test_color_presets_wrong_triplet_length_uses_default(self):
        self._write_settings([[255, 0]])
        result = load_settings(self.settings_file)
        self.assertEqual(result.color_presets, [])

    def test_color_presets_component_out_of_range_uses_default(self):
        self._write_settings([[300, 0, 0]])
        result = load_settings(self.settings_file)
        self.assertEqual(result.color_presets, [])

    def test_color_presets_component_negative_uses_default(self):
        self._write_settings([[-1, 0, 0]])
        result = load_settings(self.settings_file)
        self.assertEqual(result.color_presets, [])

    def test_color_presets_bool_component_rejected(self):
        self._write_settings([[True, 0, 0]])
        result = load_settings(self.settings_file)
        self.assertEqual(result.color_presets, [])

    def test_color_presets_non_int_component_uses_default(self):
        self._write_settings([[1.5, 0, 0]])
        result = load_settings(self.settings_file)
        self.assertEqual(result.color_presets, [])

    def test_color_presets_empty_list_accepted(self):
        self._write_settings([])
        result = load_settings(self.settings_file)
        self.assertEqual(result.color_presets, [])

    def _write_recent_settings(self, recent_value):
        payload = {
            "default_master_ip": "10.0.0.1",
            "udp_port": 55555,
            "udp_chunk_size": 1024,
            "autosave_interval_seconds": 30,
            "color_presets": [],
            "recent_project_ids": recent_value,
        }
        self.settings_file.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def test_recent_project_ids_defaults_to_empty_list(self):
        self.assertEqual(AppSettings().recent_project_ids, [])

    def test_recent_project_ids_valid_round_trip(self):
        custom = AppSettings(
            recent_project_ids=["p1", "p2", "p3"],
        )
        save_settings(custom, self.settings_file)
        loaded = load_settings(self.settings_file)
        self.assertEqual(
            loaded.recent_project_ids,
            ["p1", "p2", "p3"],
        )

    def test_recent_project_ids_non_list_uses_default(self):
        self._write_recent_settings("not a list")
        result = load_settings(self.settings_file)
        self.assertEqual(result.recent_project_ids, [])

    def test_recent_project_ids_non_string_entry_uses_default(self):
        self._write_recent_settings(["p1", 42])
        result = load_settings(self.settings_file)
        self.assertEqual(result.recent_project_ids, [])

    def test_recent_project_ids_deduplicates_preserving_order(self):
        self._write_recent_settings(["p1", "p2", "p1", "p3"])
        result = load_settings(self.settings_file)
        self.assertEqual(
            result.recent_project_ids,
            ["p1", "p2", "p3"],
        )

    def _write_templates_settings(self, templates_value):
        payload = {
            "default_master_ip": "10.0.0.1",
            "udp_port": 55555,
            "udp_chunk_size": 1024,
            "autosave_interval_seconds": 30,
            "color_presets": [],
            "recent_project_ids": [],
            "device_templates": templates_value,
        }
        self.settings_file.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def _valid_template(self, tid="tpl-1", name="T1"):
        return {
            "template_version": 1,
            "template_id": tid,
            "template_name": name,
            "slave_config": {
                "name": "S",
                "pin": "0",
                "led_count": 30,
                "id": "s1",
                "tagTypes": {},
            },
        }

    def test_device_templates_defaults_to_empty_list(self):
        self.assertEqual(AppSettings().device_templates, [])

    def test_device_templates_valid_round_trip(self):
        tpl = self._valid_template()
        custom = AppSettings(device_templates=[tpl])
        save_settings(custom, self.settings_file)
        loaded = load_settings(self.settings_file)
        self.assertEqual(loaded.device_templates, [tpl])

    def test_device_templates_wrong_outer_type_uses_default(self):
        self._write_templates_settings("not a list")
        result = load_settings(self.settings_file)
        self.assertEqual(result.device_templates, [])

    def test_device_templates_non_dict_entry_uses_default(self):
        self._write_templates_settings(
            [self._valid_template(), "not a dict"],
        )
        result = load_settings(self.settings_file)
        self.assertEqual(result.device_templates, [])

    def test_device_templates_missing_required_field_uses_default(self):
        bad = self._valid_template()
        del bad["template_id"]
        self._write_templates_settings([bad])
        result = load_settings(self.settings_file)
        self.assertEqual(result.device_templates, [])

    def test_device_templates_wrong_version_uses_default(self):
        bad = self._valid_template()
        bad["template_version"] = 2
        self._write_templates_settings([bad])
        result = load_settings(self.settings_file)
        self.assertEqual(result.device_templates, [])


if __name__ == "__main__":
    unittest.main()
