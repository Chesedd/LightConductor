"""Tests for MasterBox IP editing (Phase 11.2).

Headless-Qt tests covering the new ``setMasterIp`` method on MasterBox
and the ``editMasterIpDialog``'s OK-button behavior. MasterBox's
__init__ starts a QTimer-based ping worker; we stop it in setUp to
keep the test isolated."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from ProjectScreen.PlateLogic.MasterBox import (  # noqa: E402
    MasterBox,
    editMasterIpDialog,
)

_app: QApplication | None = None


def _ensure_app() -> QApplication:
    global _app
    existing = QApplication.instance()
    if existing is not None:
        return existing  # type: ignore[return-value]
    _app = QApplication([])
    return _app


class SetMasterIpTests(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.box = MasterBox(
            title="Alpha",
            boxID="m1",
            masterIp="10.0.0.1",
        )
        # Stop the auto-started ping timer so test side effects stay
        # bounded. ``setMasterIp`` calls ``QTimer.singleShot(0,
        # _start_ping_probe)`` — we patch the probe trigger to a no-op
        # to avoid starting a real worker during the test.
        self.box._ping_timer.stop()
        self.box._start_ping_probe = lambda: None  # type: ignore[method-assign]

    def tearDown(self) -> None:
        self.box.deleteLater()
        QApplication.processEvents()

    def test_set_master_ip_updates_field_and_label(self) -> None:
        self.box.setMasterIp("192.168.1.50")
        self.assertEqual(self.box.masterIp, "192.168.1.50")
        self.assertEqual(
            self.box.toggleButton.text(),
            "▼ Alpha (ip: 192.168.1.50)",
        )


class EditMasterIpDialogTests(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()

    def test_dialog_prefills_current_ip(self) -> None:
        dialog = editMasterIpDialog("10.0.0.1")
        self.assertEqual(dialog.masterIpBar.text(), "10.0.0.1")
        dialog.deleteLater()

    def test_ok_with_new_ip_emits_signal_and_accepts(self) -> None:
        dialog = editMasterIpDialog("10.0.0.1")
        captured: list[str] = []
        dialog.masterIpChanged.connect(captured.append)
        dialog.masterIpBar.setText("10.0.0.2")

        dialog.onOkClicked()

        self.assertEqual(captured, ["10.0.0.2"])
        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted.value)
        dialog.deleteLater()

    def test_ok_with_unchanged_ip_does_not_emit(self) -> None:
        dialog = editMasterIpDialog("10.0.0.1")
        captured: list[str] = []
        dialog.masterIpChanged.connect(captured.append)

        dialog.onOkClicked()

        self.assertEqual(captured, [])
        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted.value)
        dialog.deleteLater()

    def test_ok_with_empty_ip_is_noop(self) -> None:
        dialog = editMasterIpDialog("10.0.0.1")
        captured: list[str] = []
        dialog.masterIpChanged.connect(captured.append)
        dialog.masterIpBar.setText("   ")

        dialog.onOkClicked()

        self.assertEqual(captured, [])
        # Dialog not accepted — stays open for further input.
        self.assertNotEqual(dialog.result(), dialog.DialogCode.Accepted.value)
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
