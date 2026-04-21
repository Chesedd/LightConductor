"""Standalone popout window that hosts a :class:`LedGridView` driven
by the project's active slave. Replaces the per-slave inline preview
that used to sit above the waveform renderer.

The window is a non-modal :class:`QDialog` parented to the
``ProjectWindow`` so it auto-closes with the project. It owns the
``LedGridView`` instance, re-wires the active slave's
``wave.positionUpdate`` signal when selection changes, and
self-destructs on close (``WA_DeleteOnClose``). Re-opening rebuilds
from scratch — keeps state management trivial and avoids stale widget
issues. Window geometry is session-only (no QSettings persistence)."""

from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout

from ProjectScreen.TagLogic.LedGridView import LedGridView

INITIAL_CELL_PX = 16
DEFAULT_W = 640
DEFAULT_H = 480
SCREEN_FRAC_CAP = 0.8


class LedPreviewWindow(QDialog):
    """Popout LED preview. Follows the project's active slave."""

    def __init__(self, project_window: Any, parent: Any = None) -> None:
        super().__init__(parent if parent is not None else project_window)
        self._project_window = project_window
        self._active_slave: Any = None
        self._connected_wave: Any = None

        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("LED Preview")

        state = getattr(project_window, "state", None)
        self._grid = LedGridView(
            state=state,
            master_id=None,
            slave_id=None,
            parent=self,
            resizable=True,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._grid)

        # Subscribe to active-slave changes. The signal is a class
        # attribute on ProjectWindow (added alongside this popout).
        signal = getattr(project_window, "activeSlaveChanged", None)
        if signal is not None:
            signal.connect(self._on_active_slave_changed)

        # Seed with whatever slave is currently active.
        initial = getattr(project_window, "_active_slave", None)
        self._apply_active_slave(initial)
        self.resize(*self._initial_size(initial))

    def _initial_size(self, slave: Any) -> tuple[int, int]:
        """Pick a sensible opening size.
        - Default DEFAULT_W × DEFAULT_H.
        - If an active slave is known, scale cells × INITIAL_CELL_PX so
          the preview opens near actual pixel size. Capped at 80% of
          the available screen so we never cover the whole display.
        """
        w, h = DEFAULT_W, DEFAULT_H
        if slave is not None:
            domain = self._resolve_domain_slave(slave)
            if domain is not None:
                rows = int(getattr(domain, "grid_rows", 1) or 1)
                cols = int(getattr(domain, "grid_columns", 0) or 0)
                if rows > 0 and cols > 0:
                    w = max(DEFAULT_W, cols * INITIAL_CELL_PX + 32)
                    h = max(DEFAULT_H, rows * INITIAL_CELL_PX + 64)
        screen = self.screen()
        if screen is not None:
            geom = screen.availableGeometry()
            w = min(w, int(geom.width() * SCREEN_FRAC_CAP))
            h = min(h, int(geom.height() * SCREEN_FRAC_CAP))
        return max(200, w), max(150, h)

    def _resolve_domain_slave(self, slave: Any) -> Any:
        """Resolve the domain-level Slave object from a SlaveBox-like
        active slave. Returns None if anything is missing."""
        state = getattr(self._project_window, "state", None)
        master_id = getattr(slave, "_master_id", None)
        slave_id = getattr(slave, "boxID", None)
        if state is None or master_id is None or slave_id is None:
            return None
        try:
            return state.master(master_id).slaves[slave_id]
        except KeyError:
            return None

    def _on_active_slave_changed(self, slave: Any) -> None:
        self._apply_active_slave(slave)

    def _apply_active_slave(self, slave: Any) -> None:
        """Update internal LedGridView wiring and title to follow the
        given active slave. Disconnects the previous slave's
        ``wave.positionUpdate`` and re-connects to the new one."""
        if self._connected_wave is not None:
            try:
                self._connected_wave.positionUpdate.disconnect(
                    self._on_position_update,
                )
            except (TypeError, RuntimeError):
                pass
            self._connected_wave = None

        self._active_slave = slave
        master_id = getattr(slave, "_master_id", None)
        slave_id = getattr(slave, "boxID", None)
        self._grid._master_id = master_id
        self._grid._slave_id = slave_id
        self._grid._recompute()

        if slave is None:
            self.setWindowTitle("LED Preview")
            return

        name = getattr(slave, "title", None) or str(slave_id or "")
        self.setWindowTitle(f"LED Preview — {name}")

        wave = getattr(slave, "wave", None)
        if wave is not None and hasattr(wave, "positionUpdate"):
            wave.positionUpdate.connect(self._on_position_update)
            self._connected_wave = wave

    def _on_position_update(self, time_value: float, _time_str: str) -> None:
        self._grid.set_time(time_value)

    # Testing accessor.
    def grid_view(self) -> LedGridView:
        return self._grid

    def active_slave(self) -> Optional[Any]:
        return self._active_slave
