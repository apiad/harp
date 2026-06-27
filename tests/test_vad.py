"""Tests for harp.vad."""

import numpy as np
import pytest

from harp.vad import SileroDetector, SpeechDetector


def test_protocol_runtime_checkable():
    class Dummy:
        def speech_segments(self, audio):
            return [(0, 10)]

    assert isinstance(Dummy(), SpeechDetector)


def test_empty_audio_short_circuits_without_model():
    # size == 0 returns [] before any model load — cheap, no slow marker.
    det = SileroDetector()
    assert det.speech_segments(np.zeros(0, dtype=np.float32)) == []


@pytest.mark.slow
def test_silero_finds_no_speech_in_silence():
    det = SileroDetector()
    segs = det.speech_segments(np.zeros(16000, dtype=np.float32))
    assert segs == []


@pytest.mark.slow
def test_silero_returns_sample_index_tuples():
    det = SileroDetector()
    rng = np.random.default_rng(0)
    audio = np.concatenate(
        [
            np.zeros(8000, dtype=np.float32),
            rng.standard_normal(16000).astype(np.float32) * 0.3,
            np.zeros(8000, dtype=np.float32),
        ]
    )
    segs = det.speech_segments(audio)
    assert all(isinstance(s, tuple) and len(s) == 2 for s in segs)
    assert all(0 <= a < b <= audio.shape[0] for a, b in segs)
