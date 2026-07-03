import numpy as np
import pytest

from harp.dictation import DictationSession


class _ListSource:
    """Yields a fixed list of PCM frames, then ends. Deterministic."""

    def __init__(self, frames, sr=16000):
        self.sample_rate = sr
        self.channels = 1
        self._frames = list(frames)
        self.closed = False

    def frames(self):
        for f in self._frames:
            if self.closed:
                return
            yield f

    def close(self):
        self.closed = True


class _QueuedSource:
    """Queue-backed source mirroring MicrophoneSource: frames arrive over
    time; close() drops a None sentinel to end iteration after draining."""

    def __init__(self, sr=16000):
        import queue
        self.sample_rate = sr
        self.channels = 1
        self._q = queue.Queue()
        self.closed = False

    def push(self, frame):
        self._q.put(frame)

    def frames(self):
        while True:
            item = self._q.get()
            if item is None:
                return
            yield item

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._q.put(None)


def _frame(samples):
    return np.zeros(samples, dtype=np.int16).tobytes()


def test_no_decode_while_recording_then_one_on_stop():
    calls = {"n": 0, "lens": []}

    def transcribe(audio, prompt, language):
        calls["n"] += 1
        calls["lens"].append(int(audio.shape[0]))
        return "hello world"

    src = _ListSource([_frame(1600)] * 3)
    d = DictationSession(src, transcribe)
    d.start()
    d._worker.join(timeout=5.0)   # source ends on its own
    assert calls["n"] == 0        # nothing decoded while buffering
    text = d.stop()
    assert text == "hello world"
    assert calls["n"] == 1        # exactly one decode, on stop
    assert calls["lens"] == [3 * 1600]   # whole clip


def test_stop_drains_queued_tail():
    got = {}

    def transcribe(audio, prompt, language):
        got["len"] = int(audio.shape[0])
        return "x"

    src = _QueuedSource()
    d = DictationSession(src, transcribe)
    d.start()
    for _ in range(5):
        src.push(_frame(1600))
    # stop() closes the source (sentinel) and must drain all 5 frames.
    d.stop()
    assert got["len"] == 5 * 1600


def test_empty_buffer_returns_empty_string():
    def transcribe(audio, prompt, language):
        raise AssertionError("must not decode an empty buffer")

    d = DictationSession(_ListSource([]), transcribe)
    d.start()
    assert d.stop() == ""


def test_stop_is_idempotent():
    def transcribe(audio, prompt, language):
        return "once"

    d = DictationSession(_ListSource([_frame(800)]), transcribe)
    d.start()
    assert d.stop() == "once"
    assert d.stop() == "once"          # no re-decode, same text
    assert d.final_text == "once"


def test_max_seconds_caps_the_buffer():
    lengths = []

    def transcribe(audio, prompt, language):
        lengths.append(int(audio.shape[0]))
        return ""

    # 10 frames of 1600 samples = 16000 samples = 1.0s; cap at 0.3s.
    src = _ListSource([_frame(1600)] * 10)
    d = DictationSession(src, transcribe, max_seconds=0.3)
    d.start()
    d._worker.join(timeout=5.0)
    d.stop()
    # capped near 0.3s (4800 samples); never the full 16000.
    assert lengths[0] <= 16000 * 0.3 + 1600
    assert lengths[0] < 10 * 1600


def test_dictation_session_is_exported():
    import harp
    assert harp.DictationSession is DictationSession


@pytest.mark.slow
def test_dictation_transcribes_real_wav():
    from pathlib import Path

    from harp.whisper import LocalWhisperEngine
    from tests.fakes import FileAudioSource

    wav = Path("tests/assets/ground_truth.wav")
    eng = LocalWhisperEngine(
        model_size="base", device="cpu", compute_type="default", beam_size=1)
    d = DictationSession(FileAudioSource(wav), eng.transcribe)
    d.start()
    d._worker.join(timeout=120.0)
    text = d.stop()
    assert len(text) > 50
    assert "existence" in text.lower()
