"""
Unit tests for the Harpo daemon logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import evdev
import numpy as np
import pytest

if TYPE_CHECKING:
    from harp.daemon import HarpDaemon


@pytest.fixture
def daemon() -> HarpDaemon:
    """
    Provides a fresh HarpDaemon instance with mocked components.
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

        config = HarpConfig(toggle=True, full_mode=True)
        return HarpDaemon(config=config)


def test_daemon_initialization(daemon: HarpDaemon) -> None:
    """
    Checks if the HarpDaemon initializes with correct flags.
    """
    from harp.daemon import DaemonState

    assert daemon.state == DaemonState.IDLE
    assert daemon.config.toggle is True
    assert daemon.config.full_mode is True


@patch("subprocess.run")
def test_daemon_notify(mock_run: MagicMock, daemon: HarpDaemon) -> None:
    """
    Checks if _notify calls notify-send correctly.
    """
    daemon._notify("Title", "Short message")
    mock_run.assert_called_once()
    args, _ = mock_run.call_args
    cmd = args[0]
    assert "notify-send" in cmd
    assert "Title: Short message" in cmd


def test_release_modifiers_no_device(daemon: HarpDaemon) -> None:
    """
    Should not crash if uinput_device is None.
    """
    daemon._uinput_device = None
    daemon._release_modifiers()  # should not raise


def test_release_modifiers_with_device(daemon: HarpDaemon) -> None:
    """
    Should write EV_KEY 0 for all modifiers.
    """
    mock_uinput = MagicMock()
    daemon._uinput_device = mock_uinput

    daemon._release_modifiers()

    # There are 8 modifiers in the list
    assert mock_uinput.write.call_count == 8
    mock_uinput.syn.assert_called_once()


def test_is_real_keyboard(daemon: HarpDaemon) -> None:
    """
    Checks if the keyboard detection logic correctly filters devices.
    """
    # Mock devices
    real_kb = MagicMock(spec=evdev.InputDevice)
    real_kb.name = "Standard PS/2 Keyboard"
    real_kb.capabilities.return_value = {
        evdev.ecodes.EV_KEY: list(range(evdev.ecodes.KEY_A, evdev.ecodes.KEY_Z + 1))
    }

    our_virtual = MagicMock(spec=evdev.InputDevice)
    our_virtual.name = "Harp Virtual passthrough"

    mouse = MagicMock(spec=evdev.InputDevice)
    mouse.name = "Logitech USB Mouse"
    mouse.capabilities.return_value = {evdev.ecodes.EV_KEY: [evdev.ecodes.BTN_LEFT]}

    assert daemon._is_real_keyboard(real_kb) is True
    assert daemon._is_real_keyboard(our_virtual) is False
    assert daemon._is_real_keyboard(mouse) is False


@pytest.mark.asyncio
async def test_start_recording(daemon: HarpDaemon) -> None:
    """
    Verifies state change and audio capture start.
    """
    from harp.daemon import DaemonState

    daemon.console = MagicMock()
    daemon._notify = MagicMock()
    daemon.audio_streamer = MagicMock()

    daemon._start_recording()

    assert daemon.state == DaemonState.RECORDING
    daemon.audio_streamer.start_recording.assert_called_once()


@pytest.mark.asyncio
async def test_stop_recording_no_data(daemon: HarpDaemon) -> None:
    """
    Should just reset to IDLE if no audio data was captured.
    """
    from harp.daemon import DaemonState

    daemon.audio_streamer.stop_recording.return_value = np.array([], dtype=np.float32)
    daemon.state = DaemonState.RECORDING

    await daemon._stop_recording()

    assert daemon.state == DaemonState.IDLE
