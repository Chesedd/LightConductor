"""Pure helper for the timeline-level "Flip selected tags" action.

Mirrors the design of :mod:`ProjectScreen.TagLogic.TagClipboard`:
the heavy lifting lives here as plain Python (no Qt) so the
ProjectWindow handlers stay slim and the tests can exercise the
logic with fake controllers / scene tags.

Given a list of selected scene tags, the helper returns a single
``Command`` to push onto the project's command stack:
  * ``None`` if every selected tag was either skipped (action=off)
    or resolved to nothing.
  * A single :class:`EditTagCommand` if exactly one tag survived
    the action-off filter.
  * A :class:`CompositeCommand` wrapping all surviving
    :class:`EditTagCommand` children otherwise — one Ctrl+Z reverts
    the whole batch.

Action-off scene tags carry no meaningful color palette, so they
are skipped silently. The helper returns the count of skipped tags
alongside the command so the caller can log / surface a status
update if desired.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence, Tuple, Union

from lightconductor.application.color_flip import (
    flipped_colors_horizontal,
    flipped_colors_vertical,
)
from lightconductor.application.commands import (
    CompositeCommand,
    EditTagCommand,
)

logger = logging.getLogger(__name__)


FlipResult = Tuple[
    Optional[Union[EditTagCommand, CompositeCommand]],
    int,
]


def build_flip_commands(
    selected_scene_tags: Sequence,
    controller,
    *,
    master_id: str,
    slave_id: str,
    slave_grid_columns: int,
    axis: str,
) -> FlipResult:
    """Build the command (single or composite) that applies a
    horizontal/vertical color flip to every action-on scene tag in
    ``selected_scene_tags``.

    Returns ``(command_or_None, action_off_skipped_count)``.
    """
    if axis not in ("horizontal", "vertical"):
        raise ValueError(f"axis must be 'horizontal' or 'vertical', got {axis!r}")
    if not selected_scene_tags:
        return None, 0
    flip = (
        flipped_colors_horizontal
        if axis == "horizontal"
        else flipped_colors_vertical
    )
    children: List[EditTagCommand] = []
    skipped_action_off = 0
    for scene_tag in selected_scene_tags:
        if not bool(getattr(scene_tag, "action", False)):
            skipped_action_off += 1
            continue
        type_ = getattr(scene_tag, "type", None)
        type_name = getattr(type_, "name", None) if type_ is not None else None
        if type_name is None:
            continue
        try:
            tag_index = controller.scene_tags_for(type_name).index(scene_tag)
        except ValueError:
            continue
        topology = list(getattr(type_, "topology", []) or [])
        current_colors = [
            list(c) for c in (getattr(scene_tag, "colors", None) or [])
        ]
        try:
            new_colors = flip(topology, current_colors, slave_grid_columns)
        except ValueError as exc:
            logger.warning(
                "Flip skipped for tag %s/%s/%s: %s",
                master_id,
                slave_id,
                type_name,
                exc,
            )
            continue
        children.append(
            EditTagCommand(
                master_id=master_id,
                slave_id=slave_id,
                type_name=type_name,
                tag_index=tag_index,
                new_colors=new_colors,
            )
        )
    if not children:
        return None, skipped_action_off
    if len(children) == 1:
        return children[0], skipped_action_off
    return CompositeCommand(children=children), skipped_action_off
