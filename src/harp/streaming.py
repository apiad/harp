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
# Returns (start, end, text) per segment, timestamps in seconds.
SegmentsFn = Callable[[np.ndarray, Optional[str], Optional[str]], List[tuple]]

_EPS = 1e-3  # seconds; segment-boundary tolerance for dedup


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
        transient: bool = False,
        transcribe_segments: Optional[SegmentsFn] = None,
        overlap: float = 3.0,
    ) -> None:
        self._transcribe = transcribe
        self._transcribe_segments = transcribe_segments
        self._detector = detector
        self._sr = samplerate
        self._warmup = warmup
        self._silence = silence_threshold
        self._max_segment = max_segment
        self._language = language
        self._transient = transient
        self._overlap = overlap
        self._active = np.zeros(0, dtype=np.float32)
        self._committed = ""
        # Absolute audio-time bookkeeping for overlap-based finalization.
        self._buf_start_abs = 0.0  # abs time (s) of active[0]
        self._committed_abs = 0.0  # abs time (s) committed up to

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

    def _commit_prefix(self, end_sample: int, is_final: bool = False) -> None:
        """Finalize active[:end_sample] once and drop the committed audio.

        With a segment-aware decoder, the chunk is committed by absolute audio
        time and the trailing ``overlap`` seconds are held back (re-decoded with
        full context in the next chunk), so neither the cut's tail nor the next
        chunk's onset is decoded cold mid-word. Otherwise falls back to a plain
        string decode that drops the whole prefix.
        """
        if self._transcribe_segments is not None:
            self._commit_segments(end_sample, is_final)
        else:
            chunk = self._active[:end_sample]
            text = self._decode(chunk)
            if text:
                self._committed = f"{self._committed} {text}".strip()
            self._active = self._active[end_sample:]

    def _commit_segments(self, end_sample: int, is_final: bool) -> None:
        chunk = self._active[:end_sample]
        prompt = self._committed[-200:] or None
        segments = self._transcribe_segments(chunk, prompt, self._language)
        cut_abs = self._buf_start_abs + end_sample / self._sr
        # On a mid-stream cut, don't commit the last `overlap` seconds: that
        # tail is cut mid-word and unreliable. Hold it back to be re-decoded
        # with full context next chunk. The final flush commits everything.
        hold = 0.0 if is_final else self._overlap

        def run(hold_s: float) -> bool:
            progressed = False
            for start, end, text in segments:
                abs_start = self._buf_start_abs + start
                abs_end = self._buf_start_abs + end
                text = text.strip()
                if (
                    text
                    and abs_start + _EPS >= self._committed_abs
                    and abs_end <= cut_abs - hold_s + _EPS
                ):
                    self._committed = f"{self._committed} {text}".strip()
                    self._committed_abs = abs_end
                    progressed = True
            return progressed

        # Guarantee forward progress: if holding back commits nothing (e.g. one
        # giant segment spanning the chunk), commit without holdback.
        if not run(hold) and not is_final and self._committed_abs <= cut_abs:
            run(0.0)

        # Retain exactly the uncommitted audio (the held-back tail + anything
        # past the cut) so the next decode has it with surrounding context.
        drop = int(round((self._committed_abs - self._buf_start_abs) * self._sr))
        drop = max(0, min(drop, self._active.shape[0]))
        self._active = self._active[drop:]
        self._buf_start_abs += drop / self._sr

    # ---- stepping ----

    def step(self) -> TranscriptState:
        if self._active.size == 0:
            return TranscriptState(self._committed, "")
        if self._seconds() < self._warmup:
            # Warm-up: only re-decode for a live preview when transient is on.
            # Finalize-only mode just buffers until the first boundary.
            if self._transient:
                return TranscriptState(self._committed, self._decode(self._active))
            return TranscriptState(self._committed, "")
        if self._maybe_finalize():
            return TranscriptState(self._committed, "")
        if self._transient:
            return TranscriptState(self._committed, self._decode(self._active))
        return TranscriptState(self._committed, "")

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
            self._commit_prefix(self._active.shape[0], is_final=True)
        return TranscriptState(self._committed, "")
