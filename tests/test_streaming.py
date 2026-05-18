import numpy as np
from harp.streaming import (
    StreamingTranscriber, TranscriptState, longest_common_prefix,
)


def test_longest_common_prefix():
    assert longest_common_prefix("the cat sat", "the cat ran") == "the cat "
    assert longest_common_prefix("", "abc") == ""
    assert longest_common_prefix("abc", "abc") == "abc"


def _audio(seconds=1.0, sr=16000):
    return np.zeros(int(seconds * sr), dtype=np.float32)


def test_agreement_commits_stable_prefix():
    scripted = iter(["the quick", "the quick brown", "the quick brown fox"])

    def fake(audio, prompt, lang):
        return next(scripted)

    st = StreamingTranscriber(transcribe=fake)
    st.feed(_audio())
    s1 = st.step()
    assert s1.committed == ""
    assert s1.tail == "the quick"
    st.feed(_audio())
    s2 = st.step()
    assert s2.committed == "the quick "
    assert s2.tail == "brown"
    st.feed(_audio())
    s3 = st.step()
    assert s3.committed == "the quick brown "
    assert s3.tail == "fox"
    assert s3.full == "the quick brown fox"


def test_finalize_commits_tail():
    scripted = iter(["hello wor", "hello world", "hello world"])

    def fake(audio, prompt, lang):
        return next(scripted)

    st = StreamingTranscriber(transcribe=fake)
    st.feed(_audio())
    st.step()
    st.feed(_audio())
    st.step()
    final = st.finalize()
    assert final.committed.replace("  ", " ").strip() == "hello world"
    assert final.tail == ""


def test_step_on_empty_buffer_is_safe():
    st = StreamingTranscriber(transcribe=lambda a, p, lang: "x")
    s = st.step()
    assert s == TranscriptState("", "")


def test_buffer_trims_after_commit_when_over_window():
    scripted = iter(["alpha beta", "alpha beta gamma", "alpha beta gamma delta"])

    def fake(audio, prompt, lang):
        return next(scripted)

    st = StreamingTranscriber(transcribe=fake, window=1.0, overlap=0.25)
    st.feed(_audio(seconds=2.0))
    st.step()
    st.feed(_audio(seconds=2.0))
    st.step()
    assert st._buf.shape[0] == int(0.25 * 16000)
