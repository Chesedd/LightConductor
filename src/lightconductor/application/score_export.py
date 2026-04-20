"""Flat per-tag-per-LED exporter for external analysis.

Operates on domain masters and emits either CSV or JSON bytes.
Pure: no Qt, no I/O, no audio. Mirrors compiled_show color/action
normalization but produces human-readable records, not
firmware-ready binary blobs.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List, Tuple

from lightconductor.domain.models import Master


FIELD_ORDER: Tuple[str, ...] = (
    "time_seconds",
    "master_id", "master_name", "master_ip",
    "slave_id", "slave_name", "slave_pin",
    "type_name", "type_pin",
    "led_physical_index",
    "action",
    "r", "g", "b",
)


def _safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _action_is_on(action) -> bool:
    if isinstance(action, bool):
        return action
    if isinstance(action, str):
        return action.strip().lower() in {"on", "true", "1", "yes"}
    return bool(action)


def _normalize_color(color_like) -> Tuple[int, int, int]:
    if isinstance(color_like, str):
        parts = [p.strip() for p in color_like.split(",")]
        if len(parts) == 3:
            try:
                return tuple(
                    max(0, min(255, int(p))) for p in parts
                )  # type: ignore[return-value]
            except ValueError:
                pass
        return (0, 0, 0)
    if isinstance(color_like, (list, tuple)) and len(color_like) >= 3:
        try:
            return (
                max(0, min(255, int(color_like[0]))),
                max(0, min(255, int(color_like[1]))),
                max(0, min(255, int(color_like[2]))),
            )
        except (TypeError, ValueError):
            return (0, 0, 0)
    return (0, 0, 0)


def build_score_records(
    masters: Dict[str, Master],
) -> List[Dict[str, Any]]:
    """Flatten the masters tree into per-(tag x led) records.

    Returned records are dicts keyed by FIELD_ORDER. Sort is:
    time_seconds ASC, master_id ASC, slave_id ASC, type_pin ASC
    (int), led_physical_index ASC.
    """
    records: List[Dict[str, Any]] = []
    for master_id, master in (masters or {}).items():
        for slave_id, slave in (master.slaves or {}).items():
            for type_name, tag_type in (slave.tag_types or {}).items():
                type_pin_int = _safe_int(
                    getattr(tag_type, "pin", 0),
                )
                topology = list(
                    getattr(tag_type, "topology", []) or []
                )
                for tag in (tag_type.tags or []):
                    action_bool = _action_is_on(tag.action)
                    colors = getattr(tag, "colors", None) or []
                    for i, phys_idx in enumerate(topology):
                        color_like = (
                            colors[i] if i < len(colors)
                            else (0, 0, 0)
                        )
                        r, g, b = _normalize_color(color_like)
                        records.append({
                            "time_seconds": float(tag.time_seconds),
                            "master_id": str(master_id),
                            "master_name": getattr(master, "name", "") or "",
                            "master_ip": getattr(master, "ip", "") or "",
                            "slave_id": str(slave_id),
                            "slave_name": getattr(slave, "name", "") or "",
                            "slave_pin": str(
                                getattr(slave, "pin", "")
                            ),
                            "type_name": str(type_name),
                            "type_pin": type_pin_int,
                            "led_physical_index": int(phys_idx),
                            "action": action_bool,
                            "r": int(r),
                            "g": int(g),
                            "b": int(b),
                        })
    records.sort(key=lambda rec: (
        rec["time_seconds"],
        rec["master_id"],
        rec["slave_id"],
        rec["type_pin"],
        rec["led_physical_index"],
    ))
    return records


def render_csv(records: List[Dict[str, Any]]) -> str:
    """Render records as CSV text. Header row always present.

    action rendered as "On"/"Off".
    """
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(
        buf, fieldnames=list(FIELD_ORDER),
        quoting=csv.QUOTE_MINIMAL, lineterminator="\n",
    )
    writer.writeheader()
    for rec in records:
        row = dict(rec)
        row["action"] = "On" if rec["action"] else "Off"
        writer.writerow(row)
    return buf.getvalue()


def render_json(records: List[Dict[str, Any]]) -> str:
    """Render records as a single JSON array, 2-space indented,
    ensure_ascii=False. action rendered as boolean.
    """
    return json.dumps(
        records, indent=2, ensure_ascii=False,
    ) + "\n"
