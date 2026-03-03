"""
Audio streaming and capturing logic.
"""

from typing import Any

import numpy as np
import sounddevice as sd


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
        self._stream: sd.InputStream | None = None

    def _callback(
        self, indata: np.ndarray, frames: int, time: Any, status: sd.CallbackFlags
    ) -> None:
        """
        Sounddevice callback for processing incoming audio chunks.
        """
        if status:
            print(f"Audio Callback Status: {status}")
        self.audio_buffer.append(indata.copy())

    def start_recording(self) -> None:
        """
        Starts audio capture using sounddevice.
        """
        self.audio_buffer = []
        try:
            self._stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            self._stream = None

    def get_current_buffer(self) -> np.ndarray:
        """
        Returns the current audio buffer without stopping the stream.

        Returns:
            A numpy array containing the recorded PCM data so far.
        """
        if not self.audio_buffer:
            return np.array([], dtype=np.float32)
        return np.concatenate(self.audio_buffer)

    def stop_recording(self) -> np.ndarray:
        """
        Stops audio capture and returns the buffered audio.

        Returns:
            A numpy array containing the recorded PCM data.
        """
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        data = self.get_current_buffer()
        self.audio_buffer = []
        return data
