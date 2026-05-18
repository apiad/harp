"""Pure, I/O-free streaming transcription core (LocalAgreement-2)."""

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

TranscribeFn = Callable[[np.ndarray, Optional[str], Optional[str]], str]


@dataclass(frozen=True)
class TranscriptState:
    """Immutable snapshot: committed text never changes; tail may be rewritten."""

    committed: str
    tail: str

    @property
    def full(self) -> str:
        return (self.committed + self.tail).strip()


def longest_common_prefix(a: str, b: str) -> str:
    """Character-level longest common prefix of two strings."""
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return a[:n]


class StreamingTranscriber:
    """
    Re-decodes a rolling audio window every step() and commits the longest
    word-aligned prefix that agrees across two successive hypotheses
    (LocalAgreement-2). Buffer trimming is added in Task 2.
    """

    def __init__(
        self,
        transcribe: TranscribeFn,
        samplerate: int = 16000,
        window: float = 30.0,
        overlap: float = 5.0,
        language: Optional[str] = None,
    ) -> None:
        self._transcribe = transcribe
        self._sr = samplerate
        self._window = window
        self._overlap = overlap
        self._language = language
        self._buf = np.zeros(0, dtype=np.float32)
        self._committed = ""
        self._prev_hyp = ""

    def feed(self, pcm: np.ndarray) -> None:
        self._buf = np.concatenate(
            [self._buf, np.asarray(pcm, dtype=np.float32).flatten()]
        )

    def _window_audio(self) -> np.ndarray:
        max_samples = int(self._window * self._sr)
        if self._buf.shape[0] <= max_samples:
            return self._buf
        return self._buf[-max_samples:]

    def _decode(self) -> str:
        audio = self._window_audio()
        if audio.size == 0:
            return ""
        prompt = self._committed[-200:] or None
        return self._transcribe(audio, prompt, self._language).strip()

    def step(self) -> "TranscriptState":
        if self._buf.size == 0:
            return TranscriptState(self._committed, "")
        hyp_full = self._decode()
        hyp = hyp_full
        committed_stripped = self._committed.rstrip()
        if committed_stripped and hyp.startswith(committed_stripped):
            hyp = hyp[len(committed_stripped):].lstrip()
        prev_words = self._prev_hyp.split()
        curr_words = hyp.split()
        n = 0
        for a, b in zip(prev_words, curr_words):
            if a != b:
                break
            n += 1
        if n > 0:
            agreed = " ".join(curr_words[:n]) + " "
            self._committed += agreed
            hyp = " ".join(curr_words[n:])
        self._prev_hyp = hyp
        return TranscriptState(self._committed, hyp)

    def finalize(self) -> "TranscriptState":
        """End of session: force-commit whatever the last decode yields."""
        if self._buf.size > 0:
            decoded = self._decode()
            committed_stripped = self._committed.rstrip()
            if committed_stripped and decoded.startswith(committed_stripped):
                self._committed = decoded
            else:
                self._committed += decoded
        self._prev_hyp = ""
        self._buf = np.zeros(0, dtype=np.float32)
        return TranscriptState(self._committed, "")
