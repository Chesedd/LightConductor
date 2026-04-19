import json
import logging
import os
from pathlib import Path

import soundfile as sf
import librosa

from lightconductor.domain.models import Tag, TagType
from lightconductor.infrastructure.json_mapper import pack_tag, pack_tag_type
from lightconductor.infrastructure.project_file_backup import (
    write_with_rotation,
)
from lightconductor.infrastructure.project_schema import (
    SchemaValidationError,
    load_and_migrate,
    unwrap_boxes,
    validate,
    wrap_boxes,
)

logger = logging.getLogger(__name__)


class ProjectManager():
    def __init__(self, projectName, audioFile="audio.wav", dataFile="data.json", parent=None):
        self.projectName = projectName
        self.dataFile = dataFile
        self.audioFile = audioFile
        self.audioData = self.loadAudioData()
        self.boxes = self.loadData()

    def saveAudioData(self, audio, sr):
        if audio is not None:
            sf.write(f"Projects/{self.projectName}/{self.audioFile}", audio, sr)

    def loadAudioData(self):
        path = f"Projects/{self.projectName}/{self.audioFile}"
        if os.path.exists(path):
            audio, sr = librosa.load(path, sr=None, mono=True)
            return audio, sr, path
        else: return None, None, path

    def saveData(self, masters):
        self.boxes = {}
        for masterID in masters:
            saveMaster = masters[masterID]
            slaves = saveMaster.slaves
            slavesData = {}
            for slaveID in slaves:
                saveSlave = slaves[slaveID]
                tagTypes = saveSlave.wave.manager.types
                typesData = {}
                for tagType in tagTypes:
                    type = tagTypes[tagType]
                    tagsOfType = type.tags
                    tagID = 0
                    tagsData = {}
                    for tag in tagsOfType:
                        tagsData[tagID] = self.packTag(tag)
                        tagID+=1
                    typesData[type.name] = self.packType(type, tagsData)
                slavesData[slaveID] = self.packSlave(saveSlave, typesData)
            self.boxes[masterID] = self.packMaster(saveMaster, slavesData)
        envelope = wrap_boxes(self.boxes)
        try:
            validate(envelope)
        except SchemaValidationError:
            logger.exception("Refusing to save invalid project data")
            raise
        data_path = Path(f"Projects/{self.projectName}/{self.dataFile}")
        content = json.dumps(envelope, indent=4, ensure_ascii=False).encode("utf-8")
        write_with_rotation(data_path, content)

    def packMaster(self, master, slavesData):
        masterData = {}
        masterData['name'] = master.title
        masterData['id'] = master.boxID
        masterData['ip'] = getattr(master, "masterIp", "192.168.0.129")
        masterData['slaves'] = slavesData
        return masterData

    def packSlave(self, slave, typesData):
        slavedata = {}
        slavedata['name'] = slave.title
        slavedata['pin'] = slave.slavePin
        slavedata['led_count'] = slave.ledCount
        slavedata['id'] = slave.boxID
        slavedata['tagTypes'] = typesData
        return slavedata

    def packType(self, type, tagsData):
        # Build a transient domain TagType (without tags) and run it
        # through the mapper for metadata, then splice in the already-
        # packed tagsData. This avoids a double round-trip through
        # unpack_tag/pack_tag for the tags list, preserving exact byte
        # equality for the PR #5 round-trip tests.
        domain_type = TagType(
            name=type.name,
            pin=type.pin,
            rows=type.row,
            columns=type.table,
            color=type.color,
            topology=list(type.topology),
            tags=[],
        )
        packed = pack_tag_type(domain_type)
        packed["tags"] = tagsData
        return packed

    def packTag(self, tag):
        # UI tags carry `.time`, domain Tags carry `.time_seconds`.
        # Adapt on the boundary; full UI->domain mapping is Phase 1.4.
        domain_tag = Tag(
            time_seconds=tag.time,
            action=tag.action,
            colors=tag.colors,
        )
        return pack_tag(domain_tag)

    def loadData(self):
        path = Path(f"Projects/{self.projectName}/{self.dataFile}")
        if not path.exists():
            return {}
        try:
            envelope = load_and_migrate(path)
            validate(envelope)
            return unwrap_boxes(envelope)
        except SchemaValidationError as exc:
            logger.warning(
                "data.json at %s failed schema validation: %s; "
                "starting with empty project", path, exc,
            )
            return {}

    def returnAllBoxes(self):
        return self.boxes
