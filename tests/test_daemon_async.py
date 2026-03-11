"""
Asynchronous tests for the Harpo daemon.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from harp.api import BatchResponse
from harp.daemon import DaemonState, HarpDaemon


@pytest.fixture
def async_daemon() -> HarpDaemon:
    """
    Provides a fresh HarpDaemon instance with mocked components for async tests.
    """
    with (
        patch("harp.daemon.AudioStreamer"),
        patch("harp.daemon.WaylandTyper"),
        patch("harp.daemon.OpenRouterClient"),
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

    import asyncio

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
    async_daemon.config.type_result = True
    async_daemon.state = DaemonState.RECORDING
    async_daemon.audio_streamer.stop_recording.return_value = np.array(
        [[0.1]], dtype=np.float32
    )
    async_daemon.api_client.transcribe = AsyncMock(
        return_value=BatchResponse(full_text="Final result")
    )
    async_daemon.typer.filter_text.side_effect = lambda x: x

    await async_daemon._stop_recording()

    assert async_daemon.state == DaemonState.IDLE
    async_daemon.typer.type_text.assert_called_with("Final result")
