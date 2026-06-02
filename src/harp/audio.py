"""Audio source abstraction and microphone implementation."""

from __future__ import annotations

import queue
from typing import Any, Iterable, Optional, Protocol, runtime_checkable

import sounddevice as sd


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
        self._stream: Optional[sd.InputStream] = None
        self._closed = False

    def _callback(
        self, indata: Any, frames: int, time: Any, status: sd.CallbackFlags
    ) -> None:
        # indata is float32 by default; convert to int16 bytes.
        import numpy as np

        int16 = (indata[:, 0] * 32768.0).clip(-32768, 32767).astype(np.int16)
        self._queue.put(int16.tobytes())

    def frames(self) -> Iterable[bytes]:
        if self._closed:
            return iter(())
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
            while not self._closed:
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
        self._queue.put(None)
        self._stop_stream()

    def _stop_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
