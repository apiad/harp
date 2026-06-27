"""Tests for the VAD-segmented StreamingTranscriber core."""

import numpy as np

from harp.streaming import StreamingTranscriber, TranscriptState


def _silence(seconds, sr=16000):
    return np.zeros(int(seconds * sr), dtype=np.float32)


class FakeTranscribe:
    """Returns a word count proportional to buffer seconds; records call sizes."""

    def __init__(self):
        self.calls = []  # buffer lengths (samples) it was asked to decode

    def __call__(self, audio, prompt, language):
        self.calls.append(audio.shape[0])
        words = max(1, audio.shape[0] // 16000)
        return " ".join(f"w{i}" for i in range(words))


class NoSpeech:
    def speech_segments(self, audio):
        return []


class ScriptedSpeech:
    """Reports one speech span ending `trailing_silence_s` before the buffer end."""

    def __init__(self, trailing_silence_s, sr=16000):
        self._gap = int(trailing_silence_s * sr)

    def speech_segments(self, audio):
        n = audio.shape[0]
        end = n - self._gap
        if end <= 0:
            return []
        return [(0, end)]


# ---- Task 3: warm-up + finalize ----


def test_state_full_joins():
    assert TranscriptState("a b", "c").full == "a b c"


def test_warmup_emits_transient_not_committed():
    tx = FakeTranscribe()
    st = StreamingTranscriber(tx, NoSpeech(), warmup=10.0)
    st.feed(_silence(3))
    state = st.step()
    assert state.committed == ""
    assert state.transient != ""


def test_finalize_commits_once_for_short_input():
    tx = FakeTranscribe()
    st = StreamingTranscriber(tx, NoSpeech(), warmup=10.0)
    st.feed(_silence(4))
    st.step()
    final = st.finalize()
    assert final.committed != ""
    assert final.transient == ""


# ---- Task 4: VAD boundary finalization + drop ----


def test_vad_boundary_commits_and_drops_audio():
    tx = FakeTranscribe()
    st = StreamingTranscriber(
        tx, ScriptedSpeech(trailing_silence_s=1.0), warmup=10.0, silence_threshold=0.5
    )
    st.feed(_silence(12))
    state = st.step()
    assert state.committed != ""
    assert state.transient == ""
    assert st._active.shape[0] <= 2 * 16000


def test_no_boundary_when_still_speaking():
    tx = FakeTranscribe()
    st = StreamingTranscriber(
        tx, ScriptedSpeech(trailing_silence_s=0.1), warmup=10.0, silence_threshold=0.5
    )
    st.feed(_silence(12))
    state = st.step()
    assert state.committed == ""
    assert state.transient != ""


def test_committed_is_append_only_across_two_chunks():
    tx = FakeTranscribe()
    st = StreamingTranscriber(
        tx, ScriptedSpeech(trailing_silence_s=1.0), warmup=10.0, silence_threshold=0.5
    )
    st.feed(_silence(12))
    first = st.step().committed
    st.feed(_silence(12))
    second = st.step().committed
    assert second.startswith(first)
    assert len(second) > len(first)


def test_finalized_audio_never_re_decoded():
    """transcribe is never asked to decode more than ~max_segment of audio."""
    tx = FakeTranscribe()
    st = StreamingTranscriber(
        tx,
        ScriptedSpeech(trailing_silence_s=1.0),
        warmup=10.0,
        silence_threshold=0.5,
        max_segment=25.0,
    )
    for _ in range(5):
        st.feed(_silence(12))
        st.step()
    st.finalize()
    assert max(tx.calls) <= 26 * 16000  # bounded — no growing re-decode


# ---- Task 5: force-cut ----


def test_force_cut_when_no_silence_exceeds_max_segment():
    tx = FakeTranscribe()
    st = StreamingTranscriber(
        tx,
        ScriptedSpeech(trailing_silence_s=0.0),
        warmup=10.0,
        silence_threshold=0.5,
        max_segment=25.0,
    )
    st.feed(_silence(30))
    state = st.step()
    assert state.committed != ""
    assert st._active.shape[0] <= 6 * 16000
