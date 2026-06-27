"""Pure, I/O-free VAD-segmented streaming transcription core.

The engine buffers audio and, during a short warm-up window, previews a
transient hypothesis of the whole buffer (matching today's short-dictation
behaviour). Past warm-up it enters chunked mode: whenever the injected speech
detector reports trailing silence after speech — or the active buffer exceeds
``max_segment`` with no pause — it finalizes that chunk by decoding it exactly
once, appending the text to an append-only ``committed`` string, and dropping
the chunk's audio. Finalized audio is never re-decoded, which bounds per-step
cost and keeps the engine real-time for arbitrarily long input.

The class is dependency-injected: it receives a ``transcribe`` callable and a
``SpeechDetector`` so it can be exercised with fakes, no model load.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np

TranscribeFn = Callable[[np.ndarray, Optional[str], Optional[str]], str]


@dataclass(frozen=True)
class TranscriptState:
    """Immutable snapshot: committed is append-only; transient may change."""

    committed: str
    transient: str

    @property
    def full(self) -> str:
        return f"{self.committed} {self.transient}".strip()


class StreamingTranscriber:
    def __init__(
        self,
        transcribe: TranscribeFn,
        detector,  # harp.vad.SpeechDetector
        samplerate: int = 16000,
        warmup: float = 10.0,
        silence_threshold: float = 0.5,
        max_segment: float = 25.0,
        language: Optional[str] = None,
    ) -> None:
        self._transcribe = transcribe
        self._detector = detector
        self._sr = samplerate
        self._warmup = warmup
        self._silence = silence_threshold
        self._max_segment = max_segment
        self._language = language
        self._active = np.zeros(0, dtype=np.float32)
        self._committed = ""

    # ---- input ----

    def feed(self, pcm: np.ndarray) -> None:
        self._active = np.concatenate(
            [self._active, np.asarray(pcm, dtype=np.float32).flatten()]
        )

    # ---- helpers ----

    def _seconds(self) -> float:
        return self._active.shape[0] / self._sr

    def _decode(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        prompt = self._committed[-200:] or None
        return self._transcribe(audio, prompt, self._language).strip()

    def _commit_prefix(self, end_sample: int) -> None:
        """Decode active[:end_sample] once, append to committed, drop it."""
        chunk = self._active[:end_sample]
        text = self._decode(chunk)
        if text:
            self._committed = f"{self._committed} {text}".strip()
        self._active = self._active[end_sample:]

    # ---- stepping ----

    def step(self) -> TranscriptState:
        if self._active.size == 0:
            return TranscriptState(self._committed, "")
        if self._seconds() < self._warmup:
            return TranscriptState(self._committed, self._decode(self._active))
        if self._maybe_finalize():
            return TranscriptState(self._committed, "")
        return TranscriptState(self._committed, self._decode(self._active))

    def _maybe_finalize(self) -> bool:
        """Finalize a chunk if a boundary is reached. Returns True if it did."""
        segments: List[Tuple[int, int]] = self._detector.speech_segments(self._active)
        if segments:
            last_end = segments[-1][1]
            trailing = self._active.shape[0] - last_end
            if trailing >= int(self._silence * self._sr) and last_end > 0:
                self._commit_prefix(last_end)
                return True
        if self._seconds() > self._max_segment:
            self._commit_prefix(int(self._max_segment * self._sr))
            return True
        return False

    def finalize(self) -> TranscriptState:
        """End of session: commit whatever audio remains, once."""
        if self._active.size > 0:
            self._commit_prefix(self._active.shape[0])
        return TranscriptState(self._committed, "")
