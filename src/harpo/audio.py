"""
Audio streaming and capturing logic.
"""

from typing import Any

import numpy as np
import sounddevice as sd  # noqa: F401


class AudioStreamer:
    """
    Captures raw PCM audio from the microphone.
    """

    def __init__(self, samplerate: int = 16000) -> None:
        """
        Initializes the AudioStreamer.

        Args:
            samplerate: Sample rate for audio capture (default 16kHz).
        """
        self.samplerate: int = samplerate
        self.audio_buffer: list[np.ndarray] = []

    def start_recording(self) -> None:
        """
        Starts audio capture using sounddevice.
        """
        # Example of use:
        # with sd.InputStream(samplerate=self.samplerate):
        #     pass
        pass

    def stop_recording(self) -> np.ndarray:
        """
        Stops audio capture and returns the buffered audio.

        Returns:
            A numpy array containing the recorded PCM data.
        """
        # Placeholder for stopping and returning buffer.
        return np.array([], dtype=np.float32)

    def _callback(
        self, indata: np.ndarray, frames: int, time: Any, status: Any
    ) -> None:
        """
        Sounddevice callback for processing incoming audio chunks.
        """
        pass
