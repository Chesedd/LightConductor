from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(slots=True)
class Tag:
    time_seconds: float
    action: bool
    colors: List[List[int]] = field(default_factory=list)


@dataclass(slots=True)
class TagType:
    name: str
    pin: str
    rows: int
    columns: int
    color: List[int] = field(default_factory=lambda: [255, 255, 255])
    topology: List[int] = field(default_factory=list)
    tags: List[Tag] = field(default_factory=list)


@dataclass(slots=True)
class Slave:
    id: str
    name: str
    pin: str
    tag_types: Dict[str, TagType] = field(default_factory=dict)


@dataclass(slots=True)
class Master:
    id: str
    name: str
    slaves: Dict[str, Slave] = field(default_factory=dict)


@dataclass(slots=True)
class Project:
    id: str
    name: str
    song_name: str = ""
    masters: Dict[str, Master] = field(default_factory=dict)
