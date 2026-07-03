"""Tests for harp.audio.FileSource."""

import wave
from pathlib import Path

import numpy as np
import pytest

from harp.audio import AudioSource, FileSource


def _write_wav(path: Path, seconds=1.0, sr=16000):
    data = np.zeros(int(seconds * sr), dtype=np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def test_filesource_is_audiosource(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p)
    src = FileSource(p)
    assert isinstance(src, AudioSource)
    assert src.sample_rate == 16000
    assert src.channels == 1


def test_filesource_yields_int16_frames_covering_duration(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, seconds=1.0)
    src = FileSource(p, block_ms=100)
    total = b"".join(src.frames())
    samples = np.frombuffer(total, dtype=np.int16)
    assert abs(samples.shape[0] - 16000) <= 1600


def test_filesource_missing_file_raises(tmp_path):
    with pytest.raises((FileNotFoundError, OSError, ValueError, RuntimeError)):
        list(FileSource(tmp_path / "nope.wav").frames())


def test_filesource_close_does_not_truncate_decoded_audio(tmp_path):
    # close() must not abandon already-decoded audio mid-iteration — the same
    # graceful-drain principle MicrophoneSource documents. A consumer that
    # closes the source (e.g. DictationSession.stop()) then keeps draining must
    # still receive the whole clip, not a clipped tail.
    p = tmp_path / "a.wav"
    _write_wav(p, seconds=1.0)
    src = FileSource(p, block_ms=100)
    it = src.frames()
    first = next(it)  # begin decoding + yielding
    src.close()  # graceful: the rest of the already-decoded clip must survive
    total = first + b"".join(it)
    samples = np.frombuffer(total, dtype=np.int16)
    assert abs(samples.shape[0] - 16000) <= 1600
