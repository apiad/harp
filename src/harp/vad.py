"""Streaming voice-activity detection over 16 kHz float32 audio."""

from __future__ import annotations

from typing import List, Protocol, Tuple, runtime_checkable

import numpy as np


@runtime_checkable
class SpeechDetector(Protocol):
    """Returns speech spans as (start_sample, end_sample) tuples."""

    def speech_segments(self, audio: np.ndarray) -> List[Tuple[int, int]]: ...


class SileroDetector:
    """SpeechDetector backed by the Silero VAD bundled with faster-whisper.

    The Silero model is loaded lazily on the first ``speech_segments`` call,
    so constructing a detector is cheap and import-safe.
    """

    def __init__(self, threshold: float = 0.5, min_silence_ms: int = 300) -> None:
        from faster_whisper.vad import VadOptions

        self._options = VadOptions(
            threshold=threshold,
            min_silence_duration_ms=min_silence_ms,
        )
        self._sr = 16000

    def speech_segments(self, audio: np.ndarray) -> List[Tuple[int, int]]:
        from faster_whisper.vad import get_speech_timestamps

        if audio.size == 0:
            return []
        audio = np.ascontiguousarray(audio, dtype=np.float32)
        spans = get_speech_timestamps(
            audio, vad_options=self._options, sampling_rate=self._sr
        )
        return [(int(s["start"]), int(s["end"])) for s in spans]
