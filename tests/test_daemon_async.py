"""
Asynchronous tests for the Harp daemon.
"""

import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from harp.daemon import DaemonState, HarpDaemon


@pytest.fixture
def async_daemon() -> HarpDaemon:
    """
    Provides a fresh HarpDaemon instance with mocked components for async tests.
    """
    with (
        patch("harp.daemon.AudioStreamer"),
        patch("harp.daemon.WaylandTyper"),
        patch("harp.daemon.LocalWhisperEngine"),
        patch("harp.daemon.HarpConfig"),
    ):
        from harp.config import HarpConfig

        daemon = HarpDaemon(config=HarpConfig())
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

    events = [
        MagicMock(type=evdev.ecodes.EV_KEY, code=evdev.ecodes.KEY_LEFTCTRL, value=1),
        MagicMock(type=evdev.ecodes.EV_KEY, code=evdev.ecodes.KEY_SPACE, value=1),
        MagicMock(type=evdev.ecodes.EV_KEY, code=evdev.ecodes.KEY_SPACE, value=0),
        MagicMock(type=evdev.ecodes.EV_KEY, code=evdev.ecodes.KEY_LEFTCTRL, value=0),
    ]

    async def mock_event_loop():
        for e in events:
            yield e
        raise asyncio.CancelledError()

    mock_device.async_read_loop.return_value = mock_event_loop()

    task = asyncio.create_task(async_daemon._handle_events(mock_device))

    await asyncio.sleep(0.1)
    task.cancel()

    # Recording was triggered on key-down (it may have completed back to IDLE on space-up).
    assert async_daemon.audio_streamer.start_recording.called


@pytest.mark.asyncio
async def test_streaming_session_types_committed_text(async_daemon):
    async_daemon.config.type_result = True
    async_daemon.config.copy_result = False
    async_daemon.config.stream_window = 30.0
    async_daemon.config.stream_overlap = 5.0
    async_daemon.config.stream_slide_interval = 10.0
    async_daemon.config.local_language = None
    hypotheses = ["the cat", "the cat sat", "the cat sat down"]
    counter = {"i": 0}

    def fake_transcribe(*a, **k):
        i = min(counter["i"], len(hypotheses) - 1)
        counter["i"] += 1
        return hypotheses[i]

    async_daemon.whisper_engine.transcribe.side_effect = fake_transcribe
    async_daemon.typer.filter_text.side_effect = lambda x: x
    chunk = np.zeros(16000, dtype=np.float32)
    async_daemon.audio_streamer.get_current_buffer.return_value = chunk
    async_daemon.audio_streamer.stop_recording.return_value = chunk

    async_daemon._start_recording()
    for _ in range(3):
        await async_daemon._stream_tick()
    await async_daemon._stop_recording()

    assert async_daemon.state == DaemonState.IDLE
    typed = "".join(
        c.args[0] for c in async_daemon.typer.type_text.call_args_list
    )
    assert "the cat sat down" in typed.replace("  ", " ")


@pytest.mark.asyncio
async def test_streaming_tick_survives_transcribe_error(async_daemon):
    async_daemon.config.type_result = True
    async_daemon.config.stream_window = 30.0
    async_daemon.config.stream_overlap = 5.0
    async_daemon.config.local_language = None
    async_daemon.whisper_engine.transcribe.side_effect = RuntimeError("boom")
    async_daemon.typer.filter_text.side_effect = lambda x: x
    async_daemon.audio_streamer.get_current_buffer.return_value = np.zeros(
        16000, dtype=np.float32
    )
    async_daemon._start_recording()
    await async_daemon._stream_tick()
    assert async_daemon.state == DaemonState.RECORDING
