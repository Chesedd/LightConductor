import json
import os
import soundfile as sf
import librosa

class ProjectManager():
    def __init__(self, projectName, audioFile="audio.wav"):
        self.projectName = projectName
        self.audioFile = audioFile
        self.audioData = self.loadAudioData()

    def saveAudioData(self, audio, sr):
        if audio is not None:
            sf.write(f"Projects/{self.projectName}/{self.audioFile}", audio, sr)

    def loadAudioData(self):
        if os.path.exists(f"Projects/{self.projectName}/{self.audioFile}"):
            audio, sr = librosa.load(f"Projects/{self.projectName}/{self.audioFile}", sr=None, mono=True)
            return audio, sr
        else: return None, None