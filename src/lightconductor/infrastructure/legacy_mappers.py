from __future__ import annotations

from typing import Any, Dict

from lightconductor.domain.models import Master, Slave, Tag, TagType


class LegacyMastersMapper:
    """Convert current UI/widget structures to domain models."""

    def map_masters(self, legacy_masters: Dict[str, Any]) -> Dict[str, Master]:
        masters: Dict[str, Master] = {}

        for master_id, legacy_master in legacy_masters.items():
            master = Master(
                id=master_id,
                name=legacy_master.title,
                ip=getattr(legacy_master, "masterIp", "192.168.0.129"),
                slaves={},
            )

            for slave_id, legacy_slave in legacy_master.slaves.items():
                slave = Slave(
                    id=slave_id,
                    name=legacy_slave.title,
                    pin=legacy_slave.slavePin,
                    tag_types={},
                )

                legacy_types = legacy_slave.wave.manager.types
                for type_name, legacy_type in legacy_types.items():
                    mapped_type = TagType(
                        name=type_name,
                        pin=legacy_type.pin,
                        rows=legacy_type.row,
                        columns=legacy_type.table,
                        color=legacy_type.color,
                        topology=list(getattr(legacy_type, "topology", [])),
                        tags=[],
                    )

                    for legacy_tag in legacy_type.tags:
                        mapped_type.tags.append(
                            Tag(
                                time_seconds=legacy_tag.time,
                                action=legacy_tag.action,
                                colors=legacy_tag.colors,
                            )
                        )

                    slave.tag_types[type_name] = mapped_type

                master.slaves[slave_id] = slave

            masters[master_id] = master

        return masters
