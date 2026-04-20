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

from lightconductor.infrastructure.project_archive import (
    AUDIO_FILENAME_IN_ARCHIVE,
    DATA_FILENAME_IN_ARCHIVE,
    MANIFEST_CURRENT_VERSION,
    MANIFEST_FILENAME,
    ArchiveDataJsonInvalid,
    ArchiveDataJsonMissing,
    ArchiveInspection,
    ArchiveManifestInvalid,
    ArchiveManifestMissing,
    ArchiveReadError,
    ArchiveVersionUnsupported,
    export_project,
    extract_archive,
    inspect_archive,
)


def _valid_v1_envelope_bytes() -> bytes:
    envelope = {
        "schema_version": 1,
        "masters": {},
    }
    return (json.dumps(envelope, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _write_manifest(zf, extra_overrides=None):
    manifest = {
        "manifest_version": 1,
        "exported_at": "2025-01-01T00:00:00+00:00",
        "source_project_name": "Demo",
        "song_name": "Song",
        "source_created_at": "2024-06-15T10:00:00",
        "data_schema_version": 1,
        "has_audio": False,
    }
    if extra_overrides:
        manifest.update(extra_overrides)
    zf.writestr(
        "manifest.json",
        json.dumps(manifest, indent=2).encode("utf-8"),
    )


def _fake_wav_bytes() -> bytes:
    # Minimal 44-byte-ish WAV-looking blob. We never decode.
    return b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00" + b"\x00" * 20


class ExportProjectTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _make_project(self, with_audio: bool = False) -> Path:
        project_dir = self.tmp / "proj"
        project_dir.mkdir()
        (project_dir / "data.json").write_bytes(_valid_v1_envelope_bytes())
        if with_audio:
            (project_dir / "audio.wav").write_bytes(_fake_wav_bytes())
        return project_dir

    def test_export_writes_zip_with_manifest_data_no_audio(self):
        project_dir = self._make_project(with_audio=False)
        output_zip = self.tmp / "out.zip"

        export_project(
            project_dir=project_dir,
            project_name="My Project",
            song_name="My Song",
            source_created_at="2024-06-15T10:00:00",
            output_zip=output_zip,
        )

        self.assertTrue(output_zip.exists())
        with zipfile.ZipFile(output_zip, "r") as zf:
            names = set(zf.namelist())
            self.assertEqual(
                names,
                {MANIFEST_FILENAME, DATA_FILENAME_IN_ARCHIVE},
            )
            manifest = json.loads(zf.read(MANIFEST_FILENAME))
            self.assertEqual(manifest["manifest_version"], 1)
            self.assertFalse(manifest["has_audio"])
            self.assertEqual(manifest["source_project_name"], "My Project")
            self.assertEqual(manifest["song_name"], "My Song")
            self.assertEqual(
                manifest["source_created_at"],
                "2024-06-15T10:00:00",
            )
            self.assertEqual(
                zf.read(DATA_FILENAME_IN_ARCHIVE),
                _valid_v1_envelope_bytes(),
            )

    def test_export_includes_audio_when_present(self):
        project_dir = self._make_project(with_audio=True)
        output_zip = self.tmp / "out.zip"

        export_project(
            project_dir=project_dir,
            project_name="P",
            song_name="S",
            source_created_at="",
            output_zip=output_zip,
        )

        with zipfile.ZipFile(output_zip, "r") as zf:
            names = set(zf.namelist())
            self.assertEqual(
                names,
                {
                    MANIFEST_FILENAME,
                    DATA_FILENAME_IN_ARCHIVE,
                    AUDIO_FILENAME_IN_ARCHIVE,
                },
            )
            manifest = json.loads(zf.read(MANIFEST_FILENAME))
            self.assertTrue(manifest["has_audio"])
            self.assertEqual(
                zf.read(AUDIO_FILENAME_IN_ARCHIVE),
                _fake_wav_bytes(),
            )

    def test_export_fails_when_data_json_missing(self):
        project_dir = self.tmp / "proj"
        project_dir.mkdir()
        (project_dir / "audio.wav").write_bytes(_fake_wav_bytes())
        output_zip = self.tmp / "out.zip"

        with self.assertRaises(FileNotFoundError):
            export_project(
                project_dir=project_dir,
                project_name="P",
                song_name="S",
                source_created_at="",
                output_zip=output_zip,
            )

    def test_export_atomic_replaces_existing_output(self):
        project_dir = self._make_project(with_audio=False)
        output_zip = self.tmp / "out.zip"
        output_zip.write_bytes(b"garbage not a zip")

        export_project(
            project_dir=project_dir,
            project_name="P",
            song_name="S",
            source_created_at="",
            output_zip=output_zip,
        )

        with zipfile.ZipFile(output_zip, "r") as zf:
            self.assertIn(MANIFEST_FILENAME, zf.namelist())
        tmp_path = output_zip.with_suffix(output_zip.suffix + ".tmp")
        self.assertFalse(tmp_path.exists())

    def test_export_cleans_up_tmp_on_success(self):
        # Simpler variant: success path leaves no .tmp file.
        project_dir = self._make_project(with_audio=True)
        output_zip = self.tmp / "nested" / "out.zip"

        export_project(
            project_dir=project_dir,
            project_name="P",
            song_name="S",
            source_created_at="",
            output_zip=output_zip,
        )

        self.assertTrue(output_zip.exists())
        tmp_path = output_zip.with_suffix(output_zip.suffix + ".tmp")
        self.assertFalse(tmp_path.exists())


class InspectArchiveTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _build_zip(self, name: str = "archive.zip") -> Path:
        return self.tmp / name

    def test_inspect_valid_archive_returns_parsed_manifest(self):
        zip_path = self._build_zip()
        data_bytes = _valid_v1_envelope_bytes()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            _write_manifest(zf)
            zf.writestr(DATA_FILENAME_IN_ARCHIVE, data_bytes)

        inspection = inspect_archive(zip_path)

        self.assertIsInstance(inspection, ArchiveInspection)
        self.assertEqual(inspection.manifest["source_project_name"], "Demo")
        self.assertEqual(inspection.manifest["song_name"], "Song")
        self.assertEqual(inspection.data_json_bytes, data_bytes)
        self.assertIsNone(inspection.audio_wav_bytes)
        self.assertFalse(inspection.has_audio)
        self.assertEqual(inspection.source_project_name, "Demo")
        self.assertEqual(inspection.song_name, "Song")
        self.assertEqual(
            inspection.source_created_at,
            "2024-06-15T10:00:00",
        )

    def test_inspect_valid_archive_with_audio(self):
        zip_path = self._build_zip()
        audio = _fake_wav_bytes()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            _write_manifest(zf, {"has_audio": True})
            zf.writestr(DATA_FILENAME_IN_ARCHIVE, _valid_v1_envelope_bytes())
            zf.writestr(AUDIO_FILENAME_IN_ARCHIVE, audio)

        inspection = inspect_archive(zip_path)

        self.assertTrue(inspection.has_audio)
        self.assertEqual(inspection.audio_wav_bytes, audio)

    def test_inspect_rejects_non_zip_file(self):
        bogus = self.tmp / "bogus.zip"
        bogus.write_text("this is just plain text, not a zip")

        with self.assertRaises(ArchiveReadError):
            inspect_archive(bogus)

    def test_inspect_rejects_archive_without_manifest(self):
        zip_path = self._build_zip()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(DATA_FILENAME_IN_ARCHIVE, _valid_v1_envelope_bytes())

        with self.assertRaises(ArchiveManifestMissing):
            inspect_archive(zip_path)

    def test_inspect_rejects_invalid_manifest_json(self):
        zip_path = self._build_zip()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(MANIFEST_FILENAME, b"not json {{")
            zf.writestr(DATA_FILENAME_IN_ARCHIVE, _valid_v1_envelope_bytes())

        with self.assertRaises(ArchiveManifestInvalid):
            inspect_archive(zip_path)

    def test_inspect_rejects_manifest_missing_required_fields(self):
        zip_path = self._build_zip()
        manifest = {
            "manifest_version": 1,
            # exported_at is intentionally omitted
            "source_project_name": "Demo",
            "data_schema_version": 1,
            "has_audio": False,
        }
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(MANIFEST_FILENAME, json.dumps(manifest).encode())
            zf.writestr(DATA_FILENAME_IN_ARCHIVE, _valid_v1_envelope_bytes())

        with self.assertRaises(ArchiveManifestInvalid) as cm:
            inspect_archive(zip_path)
        self.assertIn("exported_at", str(cm.exception))

    def test_inspect_rejects_newer_manifest_version(self):
        zip_path = self._build_zip()
        future_version = MANIFEST_CURRENT_VERSION + 1
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            _write_manifest(zf, {"manifest_version": future_version})
            zf.writestr(DATA_FILENAME_IN_ARCHIVE, _valid_v1_envelope_bytes())

        with self.assertRaises(ArchiveVersionUnsupported):
            inspect_archive(zip_path)

    def test_inspect_rejects_archive_without_data_json(self):
        zip_path = self._build_zip()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            _write_manifest(zf)

        with self.assertRaises(ArchiveDataJsonMissing):
            inspect_archive(zip_path)

    def test_inspect_rejects_invalid_data_json(self):
        zip_path = self._build_zip()
        # data.json that fails schema validation: a list, not a dict.
        bad_data = json.dumps([1, 2, 3]).encode("utf-8")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            _write_manifest(zf)
            zf.writestr(DATA_FILENAME_IN_ARCHIVE, bad_data)

        with self.assertRaises(ArchiveDataJsonInvalid):
            inspect_archive(zip_path)


class ExtractArchiveTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _make_inspection(self, with_audio: bool = True) -> ArchiveInspection:
        return ArchiveInspection(
            manifest={
                "manifest_version": 1,
                "exported_at": "2025-01-01T00:00:00+00:00",
                "source_project_name": "Demo",
                "song_name": "Song",
                "source_created_at": "2024-06-15T10:00:00",
                "data_schema_version": 1,
                "has_audio": with_audio,
            },
            data_json_bytes=_valid_v1_envelope_bytes(),
            audio_wav_bytes=_fake_wav_bytes() if with_audio else None,
        )

    def test_extract_writes_data_and_audio_to_target_dir(self):
        inspection = self._make_inspection(with_audio=True)
        target = self.tmp / "out" / "proj"

        extract_archive(inspection, target)

        data_path = target / "data.json"
        audio_path = target / "audio.wav"
        self.assertTrue(data_path.exists())
        self.assertTrue(audio_path.exists())
        self.assertEqual(data_path.read_bytes(), _valid_v1_envelope_bytes())
        self.assertEqual(audio_path.read_bytes(), _fake_wav_bytes())

    def test_extract_overwrites_existing_files(self):
        target = self.tmp / "proj"
        target.mkdir()
        (target / "data.json").write_bytes(b"stale contents")
        (target / "audio.wav").write_bytes(b"stale audio")

        inspection = self._make_inspection(with_audio=True)
        extract_archive(inspection, target)

        self.assertEqual(
            (target / "data.json").read_bytes(),
            _valid_v1_envelope_bytes(),
        )
        self.assertEqual(
            (target / "audio.wav").read_bytes(),
            _fake_wav_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
