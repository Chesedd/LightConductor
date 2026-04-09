from __future__ import annotations

import os.path

import librosa


class LibrosaAudioLoader:
    """Audio loading adapter for project screen."""

    def load(self, file_path: str):
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)
        audio, sample_rate = librosa.load(file_path, sr=None, mono=True)
        return audio, sample_rate, file_path
