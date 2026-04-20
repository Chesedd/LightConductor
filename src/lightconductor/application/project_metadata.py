"""Read-only DTO for MainScreen project cards.

Aggregates registry metadata with per-project data.json and
audio.wav presence. Pure application layer; no Qt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True, frozen=True)
class ProjectMetadata:
    id: str
    project_name: str
    song_name: str
    created_at: Optional[str]
    modified_at: Optional[str]
    masters_count: int
    slaves_count: int
    track_present: bool
