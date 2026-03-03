"""
Tests for the AudioStreamer.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from harp.audio import AudioStreamer


@pytest.fixture
def audio_streamer() -> AudioStreamer:
    """
    Provides a fresh AudioStreamer instance.
    """
    return AudioStreamer(samplerate=16000)


def test_audio_initial_state(audio_streamer: AudioStreamer) -> None:
    """
    Verifies the initial state of the AudioStreamer.
    """
    assert audio_streamer.samplerate == 16000
    assert audio_streamer.audio_buffer == []
    assert audio_streamer._stream is None


def test_audio_callback(audio_streamer: AudioStreamer) -> None:
    """
    Checks if the callback correctly appends data to the buffer.
    """
    data = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    # Test with status (covers line 39)
    mock_status = MagicMock()
    mock_status.__bool__.return_value = True
    audio_streamer._callback(data, 3, None, mock_status)
    assert len(audio_streamer.audio_buffer) == 1
    assert np.array_equal(audio_streamer.audio_buffer[0], data)


def test_get_current_buffer(audio_streamer: AudioStreamer) -> None:
    """
    Verifies concatenation of multiple buffer chunks.
    """
    chunk1 = np.array([0.1, 0.2], dtype=np.float32)
    chunk2 = np.array([0.3, 0.4], dtype=np.float32)
    audio_streamer.audio_buffer = [chunk1, chunk2]

    full_buffer = audio_streamer.get_current_buffer()
    expected = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    assert np.array_equal(full_buffer, expected)


def test_get_current_buffer_empty(audio_streamer: AudioStreamer) -> None:
    """
    Checks behavior when buffer is empty.
    """
    full_buffer = audio_streamer.get_current_buffer()
    assert full_buffer.size == 0
    assert full_buffer.dtype == np.float32


@patch("sounddevice.InputStream")
def test_start_stop_recording(
    mock_input_stream: MagicMock, audio_streamer: AudioStreamer
) -> None:
    """
    Verifies start and stop recording logic.
    """
    mock_instance = mock_input_stream.return_value

    audio_streamer.start_recording()
    assert mock_input_stream.called
    assert audio_streamer._stream == mock_instance
    mock_instance.start.assert_called_once()

    # Simulate some data
    audio_streamer.audio_buffer = [np.array([0.5], dtype=np.float32)]

    data = audio_streamer.stop_recording()
    mock_instance.stop.assert_called_once()
    mock_instance.close.assert_called_once()
    assert audio_streamer._stream is None
    assert audio_streamer.audio_buffer == []
    assert data.size == 1
    assert data[0] == 0.5


@patch("sounddevice.InputStream", side_effect=Exception("Hardware failure"))
def test_start_recording_error(
    mock_input_stream: MagicMock, audio_streamer: AudioStreamer
) -> None:
    """
    Verifies error handling when starting audio fails (covers lines 50-52).
    """
    audio_streamer.start_recording()
    assert audio_streamer._stream is None
