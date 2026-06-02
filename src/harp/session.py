"""HarpSession: library-facing wrapper around the streaming decode loop."""

from __future__ import annotations

import queue
import threading
import time
from typing import Iterator, Optional

import numpy as np

from harp.audio import AudioSource
from harp.events import CommitEvent
from harp.streaming import StreamingTranscriber, TranscribeFn

_SENTINEL = object()


class HarpSession:
    """Drives one transcription session.

    Lifecycle:

        with HarpSession(audio=..., transcribe=...) as session:
            for event in session.events():
                ...
            print(session.final_text)

    Threading model:
        * The calling thread drives ``events()`` and reads from a queue.
        * A worker thread pulls frames from ``audio``, feeds them into a
          ``StreamingTranscriber``, and pushes ``CommitEvent``s onto the queue.
        * ``stop()`` is thread-safe and signals the worker to drain.

    ``stop()`` and ``__exit__`` both close the audio source and join the
    worker. They are idempotent.
    """

    def __init__(
        self,
        audio: AudioSource,
        transcribe: TranscribeFn,
        slide_interval: float = 1.0,
        window: float = 30.0,
        overlap: float = 5.0,
        language: Optional[str] = None,
    ) -> None:
        self._audio = audio
        self._transcribe = transcribe
        self._slide_interval = slide_interval
        self._window = window
        self._overlap = overlap
        self._language = language

        self._transcriber = StreamingTranscriber(
            transcribe=transcribe,
            samplerate=audio.sample_rate,
            window=window,
            overlap=overlap,
            language=language,
        )

        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._started = False
        self._closed = False
        self._final_text = ""
        self._t0: float = 0.0

    def __enter__(self) -> "HarpSession":
        self._start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def _start(self) -> None:
        if self._started:
            return
        self._started = True
        self._t0 = time.monotonic()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        """Signal the session to finalize and drain. Idempotent. Thread-safe."""
        if self._closed:
            return
        self._closed = True
        self._stop_event.set()
        try:
            self._audio.close()
        except Exception:
            pass
        if self._worker is not None:
            self._worker.join(timeout=5.0)

    def events(self) -> Iterator[CommitEvent]:
        """Yield CommitEvents until the session ends."""
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                return
            yield item  # type: ignore[misc]

    @property
    def final_text(self) -> str:
        return self._final_text

    # ---- worker thread ----

    def _run(self) -> None:
        last_committed = ""
        last_step = time.monotonic()
        try:
            for chunk in self._audio.frames():
                if self._stop_event.is_set():
                    break
                pcm = self._bytes_to_float32(chunk)
                if pcm.size:
                    self._transcriber.feed(pcm)
                now = time.monotonic()
                if now - last_step >= self._slide_interval:
                    last_step = now
                    last_committed = self._step_and_emit(last_committed)
        except Exception:
            # Worker errors must not deadlock the consumer.
            pass
        finally:
            try:
                final = self._transcriber.finalize()
                if final.committed.strip() and final.committed != last_committed:
                    self._emit(final.committed)
                self._final_text = final.committed.strip()
            except Exception:
                self._final_text = last_committed.strip()
            self._queue.put(_SENTINEL)

    def _step_and_emit(self, last_committed: str) -> str:
        state = self._transcriber.step()
        if state.committed != last_committed and state.committed.strip():
            self._emit(state.committed)
            return state.committed
        return last_committed

    def _emit(self, text: str) -> None:
        stripped = text.strip()
        ev = CommitEvent(
            text=stripped,
            words=len(stripped.split()),
            ts=time.monotonic() - self._t0,
        )
        self._queue.put(ev)

    @staticmethod
    def _bytes_to_float32(buf: bytes) -> np.ndarray:
        if not buf:
            return np.zeros(0, dtype=np.float32)
        ints = np.frombuffer(buf, dtype=np.int16)
        return ints.astype(np.float32) / 32768.0
