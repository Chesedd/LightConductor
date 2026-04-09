from __future__ import annotations

from typing import Any, Dict

from ProjectScreen.ProjectManager import ProjectManager


class LegacyProjectStorage:
    """Adapter over current ProjectManager for loading/saving project session."""

    def __init__(self, manager: ProjectManager):
        self.manager = manager

    def load_audio(self):
        return self.manager.loadAudioData()

    def load_boxes(self) -> Dict[str, dict]:
        return self.manager.returnAllBoxes()

    def save_audio(self, audio: Any, sample_rate: int | None) -> None:
        self.manager.saveAudioData(audio, sample_rate)

    def save_boxes(self, masters: Dict[str, Any]) -> None:
        self.manager.saveData(masters)
