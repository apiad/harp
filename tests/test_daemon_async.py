"""
Asynchronous tests for the Harpo daemon.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

if TYPE_CHECKING:
    from harp.daemon import HarpDaemon


@pytest.fixture
def async_daemon() -> HarpDaemon:
    """
    Provides a fresh HarpDaemon instance with mocked components for async tests.
    """
    from harp.daemon import HarpDaemon

    with (
        patch("harp.daemon.AudioStreamer"),
        patch("harp.daemon.WaylandTyper"),
        patch("harp.daemon.LLMClient"),
        patch("harp.daemon.LocalWhisperEngine"),
        patch("harp.daemon.HarpConfig"),
    ):
        from harp.config import HarpConfig

        daemon = HarpDaemon(config=HarpConfig())
        # Ensure UI console is mocked to avoid output clutter
        daemon.console = MagicMock()
        daemon._notify = MagicMock()
        return daemon


@pytest.mark.asyncio
async def test_handle_events_ctrl_space(async_daemon: HarpDaemon) -> None:
    """
    Mocks evdev events to simulate Ctrl+Space and verify state change.
    """
    import evdev

    from harp.daemon import DaemonState

    mock_device = MagicMock(spec=evdev.InputDevice)

    # Sequence of events: Ctrl Down, Space Down, Space Up, Ctrl Up
    events = [
        MagicMock(type=evdev.ecodes.EV_KEY, code=evdev.ecodes.KEY_LEFTCTRL, value=1),
        MagicMock(type=evdev.ecodes.EV_KEY, code=evdev.ecodes.KEY_SPACE, value=1),
        MagicMock(type=evdev.ecodes.EV_KEY, code=evdev.ecodes.KEY_SPACE, value=0),
        MagicMock(type=evdev.ecodes.EV_KEY, code=evdev.ecodes.KEY_LEFTCTRL, value=0),
    ]

    # Convert to a mock iterator for async for
    async def mock_event_loop():
        for e in events:
            yield e
        # stop the loop by raising CancelledError or just finishing
        raise asyncio.CancelledError()

    mock_device.async_read_loop.return_value = mock_event_loop()

    # Run handler in a task
    task = asyncio.create_task(async_daemon._handle_events(mock_device))

    # Give it some time to process
    await asyncio.sleep(0.1)
    task.cancel()

    # Verify that it entered recording state (non-toggle mode starts on key down)
    assert async_daemon.state != DaemonState.IDLE


@pytest.mark.asyncio
async def test_stop_recording_success(async_daemon: HarpDaemon) -> None:
    """
    Verifies full transcription process on stop.
    """
    from harp.daemon import DaemonState

    async_daemon.config.type_result = True
    async_daemon.state = DaemonState.RECORDING
    async_daemon.audio_streamer.stop_recording.return_value = np.array(
        [[0.1]], dtype=np.float32
    )

    # Mock whisper engine transcribe (called via executor)
    async_daemon.whisper_engine.transcribe.return_value = "Final result"

    # Mock typer
    async_daemon.typer.filter_text.side_effect = lambda x: x

    await async_daemon._stop_recording()

    assert async_daemon.state == DaemonState.IDLE
    async_daemon.typer.type_text.assert_called_with("Final result")


@pytest.mark.asyncio
async def test_stop_recording_command_mode(async_daemon: HarpDaemon) -> None:
    """
    Verifies command mode processing via LLMClient.
    """
    from harp.daemon import DaemonState

    async_daemon.config.type_result = True
    async_daemon._is_command_mode = True
    async_daemon.state = DaemonState.RECORDING
    async_daemon.audio_streamer.stop_recording.return_value = np.array(
        [[0.1]], dtype=np.float32
    )

    # Mock whisper engine transcribe
    async_daemon.whisper_engine.transcribe.return_value = "Run command"

    # Mock LLM client
    async_daemon.llm_client.process_text = AsyncMock(return_value="Command Output")

    # Mock typer
    async_daemon.typer.filter_text.side_effect = lambda x: x

    await async_daemon._stop_recording()

    assert async_daemon.state == DaemonState.IDLE
    async_daemon.llm_client.process_text.assert_called_once()
    async_daemon.typer.type_text.assert_called_with("Command Output")


@pytest.mark.asyncio
async def test_background_transcription_loop_continuous(
    async_daemon: HarpDaemon,
) -> None:
    """
    Verifies the incremental chunking logic in the background loop.
    """
    from harp.daemon import DaemonState

    async_daemon.config.continuous = True
    async_daemon.config.stt_min_chunk_size = 0.1
    async_daemon.config.stt_slide_interval = 0.1
    async_daemon.config.stt_overlap = 0.05
    async_daemon.state = DaemonState.RECORDING

    # Mock audio buffer: 16000 samples/sec * 0.5s = 8000 samples
    audio_data = np.zeros(8000, dtype=np.float32)
    async_daemon.audio_streamer.get_current_buffer.return_value = audio_data

    # Mock whisper engine transcribe
    async_daemon.whisper_engine.transcribe.return_value = "Incremental result"

    # Start loop in a task
    loop_task = asyncio.create_task(async_daemon._background_transcription_loop())

    # Give it some time to run at least one pass
    await asyncio.sleep(0.7)

    # Stop recording to end the loop
    async_daemon.state = DaemonState.IDLE
    await loop_task

    # Verify that transcribe was called
    assert async_daemon.whisper_engine.transcribe.called
    assert async_daemon._latest_transcription == "Incremental result"
