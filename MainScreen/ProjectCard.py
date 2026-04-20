from __future__ import annotations

from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QWidget,
)


class ProjectCard(QFrame):
    """A single project row with title, meta line, and
    actions. Emits signals for user intents; persistence and
    dialogs live in MainWindow."""

    openRequested = pyqtSignal(str)
    renameRequested = pyqtSignal(str)
    deleteRequested = pyqtSignal(str)
    exportRequested = pyqtSignal(str)

    def __init__(self, metadata: dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._metadata = dict(metadata)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { border: 1px solid #2e353d; border-radius: 10px; }"
        )
        self._build_ui()

    def project_id(self) -> str:
        return self._metadata.get("id", "")

    def project_name(self) -> str:
        return self._metadata.get("project_name", "")

    def update_metadata(self, metadata: dict) -> None:
        """Replace meta and re-render in place."""
        self._metadata = dict(metadata)
        self._title_label.setText(self._metadata.get("project_name", ""))
        self._meta_label.setText(self._build_meta_line())

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        self._title_label = QLabel(
            self._metadata.get("project_name", ""),
        )
        self._title_label.setStyleSheet(
            "QLabel { font-size: 15px; font-weight: 600; "
            "border: none; }"
        )
        top_row.addWidget(self._title_label, stretch=1)

        open_btn = QPushButton("Open")
        open_btn.setFixedHeight(32)
        open_btn.clicked.connect(
            lambda: self.openRequested.emit(self.project_id()),
        )
        export_btn = QPushButton("Export")
        export_btn.setFixedHeight(32)
        export_btn.clicked.connect(
            lambda: self.exportRequested.emit(self.project_id()),
        )
        rename_btn = QPushButton("Rename")
        rename_btn.setFixedHeight(32)
        rename_btn.clicked.connect(
            lambda: self.renameRequested.emit(self.project_id()),
        )
        delete_btn = QPushButton("Delete")
        delete_btn.setFixedHeight(32)
        delete_btn.clicked.connect(
            lambda: self.deleteRequested.emit(self.project_id()),
        )
        top_row.addWidget(open_btn)
        top_row.addWidget(export_btn)
        top_row.addWidget(rename_btn)
        top_row.addWidget(delete_btn)
        outer.addLayout(top_row)

        self._meta_label = QLabel(self._build_meta_line())
        self._meta_label.setStyleSheet(
            "QLabel { color: #9aa5b1; font-size: 12px; "
            "border: none; }"
        )
        outer.addWidget(self._meta_label)

    def _build_meta_line(self) -> str:
        parts = []
        song = self._metadata.get("song_name") or ""
        if song:
            parts.append(f"Song: {song}")
        created_fmt = self._format_iso_date(
            self._metadata.get("created_at"),
        )
        if created_fmt:
            parts.append(f"Created: {created_fmt}")
        modified_fmt = self._format_iso_date(
            self._metadata.get("modified_at"),
        )
        if modified_fmt:
            parts.append(f"Modified: {modified_fmt}")
        parts.append(
            f"Masters: {int(self._metadata.get('masters_count', 0) or 0)}"
        )
        parts.append(
            f"Slaves: {int(self._metadata.get('slaves_count', 0) or 0)}"
        )
        track = bool(self._metadata.get("track_present", False))
        parts.append(f"Track: {'yes' if track else 'no'}")
        return " · ".join(parts)

    @staticmethod
    def _format_iso_date(iso_value) -> Optional[str]:
        if not isinstance(iso_value, str) or not iso_value:
            return None
        try:
            dt = datetime.fromisoformat(iso_value)
        except ValueError:
            return None
        return dt.strftime("%d.%m.%Y")
