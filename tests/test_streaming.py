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
    st = StreamingTranscriber(tx, NoSpeech(), warmup=10.0, transient=True)
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
        tx, ScriptedSpeech(trailing_silence_s=0.1), warmup=10.0,
        silence_threshold=0.5, transient=True,
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


# ---- transient toggle (real-time finalize-only mode) ----


def test_transient_off_does_not_decode_between_boundaries():
    """With transient disabled, a non-finalizing step performs no decode."""
    tx = FakeTranscribe()
    st = StreamingTranscriber(
        tx, ScriptedSpeech(trailing_silence_s=0.1), warmup=10.0,
        silence_threshold=0.5, transient=False,
    )
    st.feed(_silence(12))
    before = len(tx.calls)
    state = st.step()  # past warmup, no boundary (0.1s < 0.5s) -> no decode
    assert state.transient == ""
    assert len(tx.calls) == before  # zero decodes performed


def test_transient_off_still_finalizes_at_boundaries():
    tx = FakeTranscribe()
    st = StreamingTranscriber(
        tx, ScriptedSpeech(trailing_silence_s=1.0), warmup=10.0,
        silence_threshold=0.5, transient=False,
    )
    st.feed(_silence(12))
    state = st.step()
    assert state.committed != ""  # boundary still finalizes (one decode)


def test_transient_off_skips_warmup_preview_decode():
    tx = FakeTranscribe()
    st = StreamingTranscriber(tx, NoSpeech(), warmup=10.0, transient=False)
    st.feed(_silence(3))
    state = st.step()
    assert state.transient == ""
    assert tx.calls == []  # nothing decoded during warm-up either


# ---- overlap + segment-timestamp dedup (tiny-model fix) ----


def _marker_audio(n_seconds, sr=16000):
    """Each 1s block is filled with its own second index as a marker value."""
    a = np.zeros(n_seconds * sr, dtype=np.float32)
    for k in range(n_seconds):
        a[k * sr : (k + 1) * sr] = float(k)
    return a


class MarkerSegments:
    """Returns one (start, end, 'w<value>') segment per 1s block of the chunk."""

    def __call__(self, audio, prompt, language):
        sr = 16000
        n = audio.shape[0] // sr
        return [
            (float(i), float(i + 1), f"w{int(round(float(audio[i * sr])))}")
            for i in range(n)
        ]


def test_overlap_dedup_no_duplicate_or_dropped_words():
    st = StreamingTranscriber(
        transcribe=lambda *a: "",
        detector=NoSpeech(),
        warmup=0.0,
        max_segment=10.0,
        overlap=3.0,
        transcribe_segments=MarkerSegments(),
    )
    st.feed(_marker_audio(30))
    for _ in range(10):  # drive successive force-cuts
        st.step()
    final = st.finalize()
    # Despite 3s overlap re-decoded each chunk, every word appears exactly once.
    assert final.committed.split() == [f"w{i}" for i in range(30)]


def test_overlap_retains_lead_in_audio():
    st = StreamingTranscriber(
        transcribe=lambda *a: "",
        detector=NoSpeech(),
        warmup=0.0,
        max_segment=10.0,
        overlap=3.0,
        transcribe_segments=MarkerSegments(),
    )
    st.feed(_marker_audio(15))
    st.step()  # one force-cut at 10s
    # 15s - (10s cut) + 3s retained overlap = 8s remains
    assert abs(st._active.shape[0] - 8 * 16000) <= 16000


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
