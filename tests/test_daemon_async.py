"""
Asynchronous tests for the HarpoDaemon.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import evdev
import numpy as np
import pytest

from harp.daemon import DaemonState, HarpoDaemon
from harp.api import BatchResponse


@pytest.fixture
def async_daemon() -> HarpoDaemon:
    """
    Provides a fresh HarpoDaemon instance with mocked components for async tests.
    """
    with (
        patch("harp.daemon.AudioStreamer"),
        patch("harp.daemon.WaylandTyper"),
        patch("harp.daemon.OpenRouterClient"),
        patch("harp.daemon.HarpoConfig"),
        patch("harp.daemon.HarpoHUD"),
    ):
        daemon = HarpoDaemon()
        # Ensure UI console is mocked to avoid output clutter
        daemon.console = MagicMock()
        daemon._notify = MagicMock()
        return daemon


@pytest.mark.asyncio
async def test_handle_events_ctrl_space(async_daemon: HarpoDaemon) -> None:
    """
    Checks if Ctrl + Space triggers recording.
    """
    mock_device = MagicMock(spec=evdev.InputDevice)

    # Simulate a sequence of events: Ctrl Down, Space Down
    event_ctrl = MagicMock()
    event_ctrl.type = evdev.ecodes.EV_KEY
    event_ctrl.code = evdev.ecodes.KEY_LEFTCTRL
    event_ctrl.value = 1  # down

    event_space = MagicMock()
    event_space.type = evdev.ecodes.EV_KEY
    event_space.code = evdev.ecodes.KEY_SPACE
    event_space.value = 1  # down

    # We need to mock categorize too because the code uses it
    with patch("evdev.categorize") as mock_cat:
        # First call returns Ctrl Down
        key_ctrl = MagicMock()
        key_ctrl.scancode = evdev.ecodes.KEY_LEFTCTRL
        key_ctrl.keystate = evdev.KeyEvent.key_down

        # Second call returns Space Down
        key_space = MagicMock()
        key_space.scancode = evdev.ecodes.KEY_SPACE
        key_space.keystate = evdev.KeyEvent.key_down

        mock_cat.side_effect = [key_ctrl, key_space]

        # Mock the async read loop
        # We want the loop to finish after two iterations
        class MockAsyncReadLoop:
            def __init__(self, events):
                self.events = events
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.events):
                    raise StopAsyncIteration
                val = self.events[self.index]
                self.index += 1
                return val

        mock_device.async_read_loop.return_value = MockAsyncReadLoop(
            [event_ctrl, event_space]
        )

        # Setup uinput mock to verify it releases modifiers
        async_daemon._uinput_device = MagicMock()

        await async_daemon._handle_events(mock_device)

        assert async_daemon.state == DaemonState.RECORDING
        assert evdev.ecodes.KEY_LEFTCTRL in async_daemon._suppressed_keys
        assert evdev.ecodes.KEY_SPACE in async_daemon._suppressed_keys


@pytest.mark.asyncio
async def test_interactive_loop_incremental(async_daemon: HarpoDaemon) -> None:
    """
    Verifies stitching in interactive loop.
    """
    async_daemon.state = DaemonState.RECORDING
    async_daemon.interactive = True
    async_daemon.interval = 0.001

    async_daemon.audio_streamer.get_rolling_window.return_value = np.array(
        [[0.1]], dtype=np.float32
    )

    # Simulation:
    # 1. Start with "Hello"
    # 2. Window returns "Hello world"
    # 3. Local stitching should result in "Hello world"
    async_daemon.api_client.transcribe = AsyncMock(
        return_value=BatchResponse(full_text="Hello world")
    )
    async_daemon.typer.filter_text.side_effect = lambda x: x

    async_daemon.current_session_text = "Hello"

    task = asyncio.create_task(async_daemon._interactive_loop())

    while async_daemon.api_client.transcribe.call_count < 1:
        await asyncio.sleep(0.001)

    async_daemon.state = DaemonState.IDLE
    await task

    async_daemon.typer.type_diff.assert_any_call("Hello", "Hello world")
    assert async_daemon.current_session_text == "Hello world"


@pytest.mark.asyncio
async def test_stop_recording_success(async_daemon: HarpoDaemon) -> None:
    """
    Verifies full transcription process on stop using type_diff.
    """
    async_daemon.state = DaemonState.RECORDING
    async_daemon.audio_streamer.stop_recording.return_value = np.array(
        [[0.1]], dtype=np.float32
    )
    async_daemon.api_client.transcribe = AsyncMock(
        return_value=BatchResponse(full_text="Final result")
    )
    async_daemon.typer.filter_text.side_effect = lambda x: x
    async_daemon.current_session_text = "Partial"

    await async_daemon._stop_recording()

    assert async_daemon.state == DaemonState.IDLE
    async_daemon.typer.type_diff.assert_called_with("Partial", "Final result")
