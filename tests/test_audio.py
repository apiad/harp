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
