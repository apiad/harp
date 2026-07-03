"""DictationSession: full (record-then-transcribe) mode for bounded
push-to-talk utterances. Buffers audio while recording and decodes the whole
clip once on stop against an injected (warm) transcribe callable. Pure of
model/mic — unit-testable with a fake AudioSource and a fake transcribe."""

from __future__ import annotations

import threading
from typing import Callable, List, Optional

from harp.audio import AudioSource, bytes_to_float32
from harp.streaming import TranscribeFn


class DictationSession:
    def __init__(
        self,
        audio: AudioSource,
        transcribe: TranscribeFn,
        language: Optional[str] = None,
        on_partial: Optional[Callable[[str], None]] = None,  # reserved, inert
        max_seconds: float = 120.0,
    ) -> None:
        self._audio = audio
        self._transcribe = transcribe
        self._language = language
        self._on_partial = on_partial  # v1: unused
        self._max_samples = int(max_seconds * audio.sample_rate)
        self._buf: List[bytes] = []
        self._worker: Optional[threading.Thread] = None
        self._started = False
        self._closed = False
        self._final_text = ""

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._worker = threading.Thread(target=self._run, name="dictation", daemon=True)
        self._worker.start()

    def _run(self) -> None:
        total = 0
        try:
            for chunk in self._audio.frames():
                self._buf.append(chunk)
                total += len(chunk) // 2  # bytes -> int16 samples
                if total >= self._max_samples:
                    break
        except Exception:  # pragma: no cover - worker must not raise out
            pass
        finally:
            # On the max-seconds cap (or any early exit) stop capture so the
            # source's queue can't keep growing. Idempotent with stop().
            try:
                self._audio.close()
            except Exception:  # pragma: no cover
                pass

    @property
    def final_text(self) -> str:
        return self._final_text

    def stop(self) -> str:
        if self._closed:
            return self._final_text
        self._closed = True
        # Closing the source ends the worker's frames() loop (mic: via its
        # None sentinel, draining everything captured; file: already ending).
        try:
            self._audio.close()
        except Exception:  # pragma: no cover
            pass
        if self._worker is not None:
            self._worker.join(timeout=5.0)
        pcm = b"".join(self._buf)
        if not pcm:
            self._final_text = ""
            return ""
        audio = bytes_to_float32(pcm)
        self._final_text = (self._transcribe(audio, None, self._language) or "").strip()
        return self._final_text
