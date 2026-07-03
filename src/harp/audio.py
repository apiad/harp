"""Audio source abstraction and microphone / file implementations."""

from __future__ import annotations

import queue
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol, Union, runtime_checkable

import numpy as np

# Lazily imported by MicrophoneSource.frames() so `import harp` stays free of
# the PortAudio dependency (warden installs the engine without sounddevice).
# Kept as a module attribute so tests can patch `harp.audio.sd`.
sd: Any = None


def bytes_to_float32(buf: bytes) -> np.ndarray:
    """Convert 16-bit mono PCM bytes to a float32 array in [-1, 1)."""
    if not buf:
        return np.zeros(0, dtype=np.float32)
    ints = np.frombuffer(buf, dtype=np.int16)
    return ints.astype(np.float32) / 32768.0


@runtime_checkable
class AudioSource(Protocol):
    """Yields PCM int16 mono frames until exhausted or closed."""

    sample_rate: int
    channels: int

    def frames(self) -> Iterable[bytes]: ...

    def close(self) -> None: ...


class MicrophoneSource:
    """Captures raw PCM audio from the default (or given) input device.

    Frames are yielded as int16 PCM bytes. The sounddevice stream is opened
    lazily on the first ``frames()`` iteration and closed when ``close()``
    is called or the iterator is exhausted.
    """

    sample_rate: int
    channels: int

    def __init__(
        self,
        sample_rate: int = 16000,
        device: Optional[str | int] = None,
        block_ms: int = 100,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = 1
        self._device = device
        self._block_frames = int(sample_rate * block_ms / 1000)
        self._queue: "queue.Queue[Optional[bytes]]" = queue.Queue()
        self._stream: Any = None
        self._closed = False

    def _callback(self, indata: Any, frames: int, time: Any, status: Any) -> None:
        # indata is float32 by default; convert to int16 bytes.
        import numpy as np

        int16 = (indata[:, 0] * 32768.0).clip(-32768, 32767).astype(np.int16)
        self._queue.put(int16.tobytes())

    def frames(self) -> Iterable[bytes]:
        if self._closed:
            return iter(())
        global sd
        if sd is None:
            import sounddevice

            sd = sounddevice
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=self._block_frames,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        return self._iter_frames()

    def _iter_frames(self) -> Iterable[bytes]:
        try:
            # Drain until the None sentinel — NOT `while not self._closed`.
            # On stop, close() sets _closed and enqueues the sentinel; bailing
            # on _closed would abandon frames already captured but not yet
            # yielded (the last utterance in push-to-talk), clipping the tail.
            while True:
                item = self._queue.get()
                if item is None:
                    return
                yield item
        finally:
            self._stop_stream()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Stop the stream FIRST so no callback can enqueue a frame past the
        # sentinel (which _iter_frames would never reach), THEN drop the
        # sentinel after the last captured frame already in the queue.
        self._stop_stream()
        self._queue.put(None)

    def _stop_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


class FileSource:
    """Decodes an audio file to 16 kHz mono int16 PCM frames.

    Uses faster-whisper's bundled decoder (PyAV), so any ffmpeg-readable
    container works (wav, m4a, mp3, ...). Frames are yielded as fast as
    decode allows — playback is not real-time-throttled.
    """

    sample_rate: int
    channels: int

    def __init__(self, path: Union[str, Path], block_ms: int = 100) -> None:
        self.sample_rate = 16000
        self.channels = 1
        self._path = str(path)
        self._block = int(self.sample_rate * block_ms / 1000)
        self._closed = False

    def frames(self) -> Iterable[bytes]:
        from faster_whisper.audio import decode_audio

        audio = decode_audio(self._path, sampling_rate=self.sample_rate)
        pcm = np.asarray(audio, dtype=np.float32) * 32768.0
        pcm = pcm.clip(-32768, 32767).astype(np.int16)
        for start in range(0, pcm.shape[0], self._block):
            if self._closed:
                return
            yield pcm[start : start + self._block].tobytes()

    def close(self) -> None:
        self._closed = True
