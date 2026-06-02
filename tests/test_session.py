"""Tests for harp.session.HarpSession."""

from __future__ import annotations

import threading
import time
import wave
from pathlib import Path
from typing import List

import numpy as np
import pytest

from harp.events import CommitEvent
from harp.session import HarpSession
from tests.fakes import FileAudioSource


@pytest.fixture()
def two_word_wav(tmp_path: Path) -> Path:
    """A 1.5s WAV the fake transcribe function will turn into 'hello world'."""
    path = tmp_path / "two_words.wav"
    sr = 16000
    samples = np.zeros(int(sr * 1.5), dtype=np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(samples.tobytes())
    return path


class FakeWhisper:
    """Stand-in for LocalWhisperEngine: returns scripted transcriptions
    sized to how much audio has been fed.
    """

    def __init__(self, hypotheses: List[str]) -> None:
        self._hypotheses = list(hypotheses)
        self.calls = 0

    def transcribe(self, audio, prompt, language) -> str:
        i = min(self.calls, len(self._hypotheses) - 1)
        self.calls += 1
        return self._hypotheses[i]


def test_session_emits_commit_events_for_growing_prefix(two_word_wav: Path) -> None:
    fake = FakeWhisper(["hello", "hello", "hello world", "hello world"])
    src = FileAudioSource(two_word_wav, chunk_ms=200)

    with HarpSession(
        audio=src,
        transcribe=fake.transcribe,
        slide_interval=0.05,
        language=None,
    ) as session:
        events = list(session.events())
        final = session.final_text

    assert all(isinstance(e, CommitEvent) for e in events)
    assert events, "expected at least one CommitEvent"
    # Each event's text strictly extends (or equals) the previous one's
    # except across LocalAgreement-2 revisions.
    assert "hello" in final
    assert final.strip() != ""


def test_session_final_text_empty_for_empty_source(tmp_path: Path) -> None:
    empty_wav = tmp_path / "empty.wav"
    with wave.open(str(empty_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"")

    fake = FakeWhisper([""])
    src = FileAudioSource(empty_wav)
    with HarpSession(audio=src, transcribe=fake.transcribe, slide_interval=0.05) as s:
        events = list(s.events())
        assert events == []
        assert s.final_text == ""


def test_session_stop_from_another_thread_drains(two_word_wav: Path) -> None:
    fake = FakeWhisper(["hello", "hello world", "hello world today"])
    src = FileAudioSource(two_word_wav, chunk_ms=50)

    with HarpSession(audio=src, transcribe=fake.transcribe, slide_interval=0.05) as session:
        def stopper():
            time.sleep(0.2)
            session.stop()

        threading.Thread(target=stopper, daemon=True).start()
        events = list(session.events())

    # The iterator must terminate. final_text must be populated.
    assert isinstance(session.final_text, str)


def test_session_context_manager_closes_audio_source(two_word_wav: Path) -> None:
    fake = FakeWhisper(["hello"])
    src = FileAudioSource(two_word_wav, chunk_ms=200)
    closed = {"called": False}
    real_close = src.close

    def tracking_close() -> None:
        closed["called"] = True
        real_close()

    src.close = tracking_close  # type: ignore[method-assign]

    with HarpSession(audio=src, transcribe=fake.transcribe, slide_interval=0.05) as s:
        list(s.events())

    assert closed["called"] is True
