import json
import os
import soundfile as sf
import librosa

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

    def saveData(self, boxes):
        self.boxes = {}
        for boxID in boxes:
            saveBox = boxes[boxID]
            tagTypes = saveBox.wave.manager.types
            typesData = {}
            for tagType in tagTypes:
                type = tagTypes[tagType]
                typeData = {}
                typeData["color"] = type.color
                typeData["pin"] = type.pin

                tagsOfType = type.tags
                tagID = 0
                tagsData = {}
                for tag in tagsOfType:
                    tagData = {}
                    tagData['time'] = tag.time
                    tagData['state'] = tag.state
                    tagsData[tagID] = tagData
                    tagID+=1
                typeData["tags"] = tagsData

                typesData[type.name] = typeData
            self.boxes[boxID] = {}
            self.boxes[boxID]['name'] = saveBox.title
            self.boxes[boxID]['id'] = saveBox.boxID
            self.boxes[boxID]['tagTypes'] = typesData
        with open(f"Projects/{self.projectName}/{self.dataFile}", 'w', encoding='utf-8') as f:
            json.dump(self.boxes, f, indent=4, ensure_ascii=False)

    def loadData(self):
        if os.path.exists(f"Projects/{self.projectName}/{self.dataFile}"):
            try:
                with open(f"Projects/{self.projectName}/{self.dataFile}", 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, KeyError):
                return {}
        return {}

    def returnAllBoxes(self):
        return self.boxes
