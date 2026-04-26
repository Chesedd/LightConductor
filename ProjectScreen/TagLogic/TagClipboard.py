"""Group-clipboard primitives for tag copy / cut / paste.

Pure-Python dataclasses and helpers — no Qt, no widget wiring.
The :class:`ProjectScreen` handlers stash a :class:`GroupClipboard`
from the current selection (``make_clipboard_from_selection``) and
rebuild a :class:`CompositeCommand` from it on paste
(``build_paste_command``). Cut combines a copy with a composite
delete (``build_cut_commands``).

Relative offsets are stored as exact float subtractions from the
group anchor (the earliest selected tag). Snapping happens later,
inside the state mutators that ``AddOrReplaceTagCommand`` invokes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from lightconductor.application.commands import (
    AddOrReplaceTagCommand,
    CompositeCommand,
    DeleteTagCommand,
)
from lightconductor.domain.models import Tag as DomainTag

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TagClipboardEntry:
    type_name: str
    relative_time: float
    action: object
    colors: Tuple[Tuple[int, ...], ...]

    def __post_init__(self) -> None:
        # Defensive hygiene; tests should not rely on this assertion.
        assert self.relative_time >= 0.0, (
            f"relative_time must be >= 0.0, got {self.relative_time!r}"
        )


@dataclass(frozen=True, slots=True)
class GroupClipboard:
    entries: Tuple[TagClipboardEntry, ...]

    @property
    def is_single_type(self) -> bool:
        if not self.entries:
            return False
        first = self.entries[0].type_name
        return all(e.type_name == first for e in self.entries)

    @property
    def lone_type_name(self) -> Optional[str]:
        return self.entries[0].type_name if self.is_single_type else None


def _freeze_colors(colors) -> Tuple[Tuple[int, ...], ...]:
    if not colors:
        return ()
    out = []
    for color in colors:
        out.append(tuple(int(c) for c in color))
    return tuple(out)


def _thaw_colors(colors: Tuple[Tuple[int, ...], ...]) -> List[List[int]]:
    return [list(c) for c in colors]


def make_clipboard_from_selection(
    selected_scene_tags: Sequence,
) -> Optional[GroupClipboard]:
    """Build a :class:`GroupClipboard` from selected scene tags.

    Reads each tag's float-seconds ``time`` attribute (not
    ``value()`` — preserves precision for rubber-band-grabbed
    tags). Returns ``None`` for an empty selection.
    """
    if not selected_scene_tags:
        return None
    times = [float(t.time) for t in selected_scene_tags]
    anchor = min(times)
    indexed = sorted(
        zip(times, selected_scene_tags),
        key=lambda p: p[0],
    )
    entries: List[TagClipboardEntry] = []
    for absolute_time, scene_tag in indexed:
        type_ = getattr(scene_tag, "type", None)
        type_name = getattr(type_, "name", None) if type_ is not None else None
        if type_name is None:
            continue
        entries.append(
            TagClipboardEntry(
                type_name=str(type_name),
                relative_time=absolute_time - anchor,
                action=scene_tag.action,
                colors=_freeze_colors(scene_tag.colors),
            )
        )
    if not entries:
        return None
    return GroupClipboard(entries=tuple(entries))


def build_paste_command(
    clipboard: GroupClipboard,
    target_manager,
    master_id: str,
    slave_id: str,
    anchor_time: float,
) -> Optional[CompositeCommand]:
    """Build a :class:`CompositeCommand` pasting all clipboard
    entries onto the target slave with times shifted to
    ``anchor_time``.

    Cross-slave guard: if any entry's ``type_name`` is missing
    on the target manager, the paste only proceeds when the
    clipboard is single-typed AND the lone type exists on the
    target. Otherwise the paste is logged at INFO level and
    blocked (returns ``None``).
    """
    if not clipboard.entries:
        return None
    target_types = getattr(target_manager, "types", {}) or {}
    all_present = all(e.type_name in target_types for e in clipboard.entries)
    if not all_present:
        if not (
            clipboard.is_single_type
            and clipboard.lone_type_name in target_types
        ):
            blocked = sorted(
                {
                    e.type_name
                    for e in clipboard.entries
                    if e.type_name not in target_types
                }
            )
            logger.info(
                "Paste blocked: target slave %s/%s missing tag type(s) %s "
                "(is_single_type=%s)",
                master_id,
                slave_id,
                blocked,
                clipboard.is_single_type,
            )
            return None
    children: List = []
    for entry in clipboard.entries:
        target_time = anchor_time + entry.relative_time
        domain_tag = DomainTag(
            time_seconds=float(target_time),
            action=entry.action,
            colors=_thaw_colors(entry.colors),
        )
        children.append(
            AddOrReplaceTagCommand(
                master_id=master_id,
                slave_id=slave_id,
                type_name=entry.type_name,
                tag=domain_tag,
            )
        )
    return CompositeCommand(children=children)


def build_cut_commands(
    selected_scene_tags: Sequence,
    controller,
    master_id: str,
    slave_id: str,
) -> Tuple[Optional[GroupClipboard], Optional[CompositeCommand]]:
    """Return ``(clipboard, composite_delete)`` for a cut.

    Resolves each tag's index via
    ``controller.scene_tags_for(type_name).index(tag)``,
    mirroring ``TagObject.deleteTag``. Children are sorted
    descending by ``tag_index`` so executing them in order leaves
    each remaining index valid (deleting a higher index never
    shifts a lower one).
    """
    clipboard = make_clipboard_from_selection(selected_scene_tags)
    if clipboard is None:
        return None, None
    children: List[DeleteTagCommand] = []
    for scene_tag in selected_scene_tags:
        type_ = getattr(scene_tag, "type", None)
        type_name = getattr(type_, "name", None) if type_ is not None else None
        if type_name is None:
            continue
        try:
            tag_index = controller.scene_tags_for(type_name).index(scene_tag)
        except ValueError:
            continue
        children.append(
            DeleteTagCommand(
                master_id=master_id,
                slave_id=slave_id,
                type_name=type_name,
                tag_index=tag_index,
            )
        )
    if not children:
        return clipboard, None
    children.sort(key=lambda c: c.tag_index, reverse=True)
    return clipboard, CompositeCommand(children=children)
