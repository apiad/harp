"""Tests for the AudioSource Protocol contract via FileAudioSource."""

import wave
from pathlib import Path

import numpy as np
import pytest

from harp.audio import AudioSource
from tests.fakes import FileAudioSource


@pytest.fixture()
def silent_wav(tmp_path: Path) -> Path:
    path = tmp_path / "silent.wav"
    sr = 16000
    samples = np.zeros(sr, dtype=np.int16)  # 1 second of silence
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(samples.tobytes())
    return path


def test_file_audio_source_satisfies_protocol(silent_wav: Path) -> None:
    src = FileAudioSource(silent_wav)
    assert isinstance(src, AudioSource)  # runtime_checkable Protocol


def test_file_audio_source_reports_sample_rate(silent_wav: Path) -> None:
    src = FileAudioSource(silent_wav)
    assert src.sample_rate == 16000
    assert src.channels == 1


def test_file_audio_source_yields_pcm_bytes(silent_wav: Path) -> None:
    src = FileAudioSource(silent_wav, chunk_ms=100)
    chunks = list(src.frames())
    # 1 second of audio at 100ms chunks → ~10 chunks.
    assert 8 <= len(chunks) <= 12
    # Each chunk is int16 PCM bytes.
    for c in chunks:
        assert isinstance(c, (bytes, bytearray))
        assert len(c) % 2 == 0  # int16 → 2 bytes per sample


def test_file_audio_source_close_is_idempotent(silent_wav: Path) -> None:
    src = FileAudioSource(silent_wav)
    src.close()
    src.close()  # no exception
