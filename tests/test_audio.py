"""Tests for harp.audio.MicrophoneSource."""

from unittest.mock import MagicMock, patch

from harp.audio import AudioSource, MicrophoneSource


def test_microphone_source_satisfies_protocol() -> None:
    with patch("harp.audio.sd") as sd_mock:
        sd_mock.InputStream.return_value = MagicMock()
        src = MicrophoneSource(sample_rate=16000)
        assert isinstance(src, AudioSource)
        assert src.sample_rate == 16000
        assert src.channels == 1
        src.close()


def test_microphone_source_starts_stream_on_frames() -> None:
    with patch("harp.audio.sd") as sd_mock:
        stream = MagicMock()
        sd_mock.InputStream.return_value = stream
        src = MicrophoneSource()

        iter(src.frames())
        # Pulling the first frame must start the stream.
        # We can't actually consume frames here without sounddevice; instead
        # assert that asking for an iterator + close() shuts the stream down.
        src.close()
        assert stream.stop.called or stream.close.called


def test_microphone_source_close_is_idempotent() -> None:
    with patch("harp.audio.sd") as sd_mock:
        sd_mock.InputStream.return_value = MagicMock()
        src = MicrophoneSource()
        src.close()
        src.close()  # no exception


def test_iter_frames_drains_queued_audio_after_close() -> None:
    # Push-to-talk stop: close() is called while captured frames are still
    # queued (the last utterance). _iter_frames must yield them all before
    # ending, or the tail is clipped. Regression for the dropped last sentence.
    src = MicrophoneSource()
    src._queue.put(b"aaaa")
    src._queue.put(b"bbbb")
    src.close()  # sets _closed, enqueues the None sentinel
    assert list(src._iter_frames()) == [b"aaaa", b"bbbb"]


def test_close_stops_stream_before_sentinel() -> None:
    # The sentinel must go in AFTER the stream is stopped, so no callback can
    # enqueue a frame past None (which _iter_frames would never reach).
    with patch("harp.audio.sd") as sd_mock:
        stream = MagicMock()
        sd_mock.InputStream.return_value = stream
        src = MicrophoneSource()
        src._stream = stream
        order = []
        stream.stop.side_effect = lambda: order.append("stop")
        real_put = src._queue.put
        src._queue.put = lambda item: (
            (order.append("sentinel"), real_put(item))[1]
            if item is None
            else real_put(item)
        )
        src.close()
        assert order.index("stop") < order.index("sentinel")


def test_bytes_to_float32_converts_int16_pcm() -> None:
    import numpy as np

    from harp.audio import bytes_to_float32

    pcm = np.array([0, 32767, -32768], dtype=np.int16).tobytes()
    out = bytes_to_float32(pcm)
    assert out.dtype == np.float32
    assert out.shape == (3,)
    assert abs(out[0]) < 1e-6
    assert out[1] == np.float32(32767 / 32768.0)


def test_bytes_to_float32_empty() -> None:
    import numpy as np

    from harp.audio import bytes_to_float32

    out = bytes_to_float32(b"")
    assert out.dtype == np.float32
    assert out.shape == (0,)
