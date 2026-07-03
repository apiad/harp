"""HarpSession: library-facing wrapper around the streaming decode loop."""

from __future__ import annotations

import queue
import threading
import time
from typing import Iterator, Optional

import numpy as np

from harp.audio import AudioSource
from harp.events import TranscriptEvent
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
          ``StreamingTranscriber``, and pushes ``TranscriptEvent``s onto the queue.
        * ``stop()`` is thread-safe and signals the worker to drain.

    ``stop()`` and ``__exit__`` both close the audio source and join the
    worker. They are idempotent.
    """

    def __init__(
        self,
        audio: AudioSource,
        transcribe: TranscribeFn,
        detector=None,  # harp.vad.SpeechDetector; defaults to NullDetector
        slide_interval: float = 1.0,
        warmup: float = 10.0,
        silence_threshold: float = 0.5,
        max_segment: float = 25.0,
        language: Optional[str] = None,
        transient: bool = False,
        transcribe_segments=None,
        overlap: float = 3.0,
    ) -> None:
        from harp.vad import NullDetector

        self._audio = audio
        self._transcribe = transcribe
        self._slide_interval = slide_interval
        self._language = language

        self._transcriber = StreamingTranscriber(
            transcribe=transcribe,
            detector=detector if detector is not None else NullDetector(),
            samplerate=audio.sample_rate,
            warmup=warmup,
            silence_threshold=silence_threshold,
            max_segment=max_segment,
            language=language,
            transient=transient,
            transcribe_segments=transcribe_segments,
            overlap=overlap,
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

    def events(self) -> Iterator[TranscriptEvent]:
        """Yield TranscriptEvents until the session ends."""
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
        # Step cadence is driven by audio-time fed, not wall-clock: a file
        # source delivers audio faster than real-time, and a wall-clock gate
        # would let the whole file arrive before the first step — collapsing
        # the stream into a single batch decode. Counting fed samples makes
        # the cadence identical for a real-time mic and a fast file alike.
        last_pair = ("", "")
        sr = self._audio.sample_rate
        step_samples = max(1, int(self._slide_interval * sr))
        pending = 0
        try:
            for chunk in self._audio.frames():
                pcm = self._bytes_to_float32(chunk)
                if pcm.size:
                    self._transcriber.feed(pcm)
                    pending += pcm.shape[0]
                # After stop is signalled, keep DRAINING the source into the
                # buffer but skip the incremental decode — the terminal
                # finalize() decodes the drained tail in one pass. Breaking
                # here instead would clip the last utterance (everything since
                # the previous silence boundary). The audio source ends the
                # loop via its own exhaustion / close() sentinel.
                if self._stop_event.is_set():
                    continue
                if pending >= step_samples:
                    pending = 0
                    last_pair = self._step_and_emit(last_pair)
        except Exception:
            # Worker errors must not deadlock the consumer.
            pass
        finally:
            try:
                final = self._transcriber.finalize()
                self._final_text = final.committed.strip()
            except Exception:
                self._final_text = last_pair[0]
            # Always emit a terminal snapshot so consumers see is_final.
            self._emit(self._final_text, "", is_final=True)
            self._queue.put(_SENTINEL)

    def _step_and_emit(self, last_pair: tuple) -> tuple:
        state = self._transcriber.step()
        pair = (state.committed.strip(), state.transient.strip())
        if pair != last_pair and (pair[0] or pair[1]):
            self._emit(pair[0], pair[1], is_final=False)
            return pair
        return last_pair

    def _emit(self, committed: str, transient: str, is_final: bool) -> None:
        ev = TranscriptEvent(
            committed=committed,
            transient=transient,
            is_final=is_final,
            ts=time.monotonic() - self._t0,
        )
        self._queue.put(ev)

    @staticmethod
    def _bytes_to_float32(buf: bytes) -> np.ndarray:
        from harp.audio import bytes_to_float32

        return bytes_to_float32(buf)
