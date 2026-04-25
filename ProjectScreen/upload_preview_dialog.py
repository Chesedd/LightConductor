"""Per-master upload preview dialog.

Renders a checkbox list of masters with a live summary that recomputes
on each toggle. The dialog is intentionally decoupled from any
``ProjectScreenController`` or domain ``Master`` object; the caller
supplies a list of plain ``MasterPreviewRow`` rows and a
``compute_summary`` callback so the dialog stays independently
testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Set, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class MasterPreviewRow:
    master_id: str
    display_name: str
    ip: str
    slaves_count: int
    blob_size_bytes: int


class UploadPreviewDialog(QDialog):
    def __init__(
        self,
        master_rows: List[MasterPreviewRow],
        compute_summary: Callable[[Set[str]], str],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm upload")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(420)

        self._compute_summary = compute_summary
        self._rows: List[Tuple[MasterPreviewRow, QCheckBox]] = []

        layout = QVBoxLayout(self)

        all_ids = {row.master_id for row in master_rows}
        self._summary_label = QLabel(compute_summary(all_ids), self)
        self._summary_label.setWordWrap(True)
        self._summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse,
        )
        layout.addWidget(self._summary_label)

        for row in master_rows:
            blob_size_kb = row.blob_size_bytes / 1024
            label = (
                f"{row.display_name}  ({row.ip})  —  "
                f"{row.slaves_count} slave(s), {blob_size_kb:.1f} KB"
            )
            cb = QCheckBox(label, self)
            cb.setChecked(True)
            cb.toggled.connect(self._recompute)
            layout.addWidget(cb)
            self._rows.append((row, cb))

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._recompute()

    def selected_master_ids(self) -> Set[str]:
        return {row.master_id for row, cb in self._rows if cb.isChecked()}

    def _recompute(self) -> None:
        selected = self.selected_master_ids()
        self._summary_label.setText(self._compute_summary(selected))
        ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(len(selected) > 0)
