"""Test-only fakes. Not part of harp's public API."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Iterable


class FileAudioSource:
    """Reads a 16-bit mono WAV and yields it in fixed-size chunks.

    Used in place of MicrophoneSource for deterministic tests. Not exported
    from the harp package.
    """

    def __init__(self, path: Path, chunk_ms: int = 100) -> None:
        self._path = Path(path)
        self._chunk_ms = chunk_ms
        with wave.open(str(self._path), "rb") as w:
            self.sample_rate = w.getframerate()
            self.channels = w.getnchannels()
            assert w.getsampwidth() == 2, "FileAudioSource requires 16-bit PCM"
        self._closed = False

    def frames(self) -> Iterable[bytes]:
        chunk_frames = int(self.sample_rate * self._chunk_ms / 1000)
        with wave.open(str(self._path), "rb") as w:
            while not self._closed:
                data = w.readframes(chunk_frames)
                if not data:
                    return
                yield data

    def close(self) -> None:
        self._closed = True
