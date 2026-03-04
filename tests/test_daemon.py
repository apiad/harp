"""
Tests for the Harp daemon.
"""

from unittest.mock import MagicMock, patch

import evdev
import numpy as np
import pytest

from harp.daemon import DaemonState, HarpoDaemon


@pytest.fixture
def daemon() -> HarpoDaemon:
    """
    Provides a fresh HarpoDaemon instance with mocked components.
    """
    with (
        patch("harp.daemon.AudioStreamer"),
        patch("harp.daemon.WaylandTyper"),
        patch("harp.daemon.OpenRouterClient"),
        patch("harp.daemon.HarpoConfig"),
    ):
        return HarpoDaemon(toggle=True, full_mode=True)


def test_daemon_initialization(daemon: HarpoDaemon) -> None:
    """
    Checks if the HarpoDaemon initializes with correct flags.
    """
    assert daemon.state == DaemonState.IDLE
    assert daemon.toggle is True
    assert daemon.full_mode is True


@patch("subprocess.run")
def test_daemon_notify(mock_run: MagicMock, daemon: HarpoDaemon) -> None:
    """
    Verifies the notification helper calls notify-send.
    """
    daemon._notify("Test Title", "Test Message")
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "notify-send" in args
    assert "Harp" in args
    assert "Test Title: Test Message" in args


def test_release_modifiers_no_device(daemon: HarpoDaemon) -> None:
    """
    Ensures _release_modifiers handles missing uinput device gracefully.
    """
    daemon._uinput_device = None
    # Should not raise
    daemon._release_modifiers()


def test_release_modifiers_with_device(daemon: HarpoDaemon) -> None:
    """
    Verifies that _release_modifiers emits UP events for modifiers.
    """
    mock_uinput = MagicMock()
    daemon._uinput_device = mock_uinput

    daemon._release_modifiers()

    # Check if write was called for common modifiers (CTRL, SHIFT, etc.)
    # There are 8 modifiers in the list, each should be set to 0 (UP)
    assert mock_uinput.write.call_count == 8
    mock_uinput.syn.assert_called_once()


def test_is_real_keyboard(daemon: HarpoDaemon) -> None:
    """
    Verifies the keyboard detection logic.
    """
    # 1. Our own virtual device (Should be False)
    mock_virt = MagicMock(spec=evdev.InputDevice)
    mock_virt.name = "Harp Virtual Keyboard"
    assert daemon._is_real_keyboard(mock_virt) is False

    # 2. Generic mouse (No 'keyboard' in name) (Should be False)
    mock_mouse = MagicMock(spec=evdev.InputDevice)
    mock_mouse.name = "Generic Mouse"
    assert daemon._is_real_keyboard(mock_mouse) is False

    # 3. Device with 'keyboard' in name but no letter keys (Should be False)
    mock_btn = MagicMock(spec=evdev.InputDevice)
    mock_btn.name = "AT Keyboard Buttons"
    mock_btn.capabilities.return_value = {evdev.ecodes.EV_KEY: [evdev.ecodes.KEY_POWER]}
    assert daemon._is_real_keyboard(mock_btn) is False

    # 4. Real keyboard (Should be True)
    mock_kb = MagicMock(spec=evdev.InputDevice)
    mock_kb.name = "Standard USB Keyboard"
    # Provide all keys from A to Z
    mock_kb.capabilities.return_value = {
        evdev.ecodes.EV_KEY: list(range(evdev.ecodes.KEY_A, evdev.ecodes.KEY_Z + 1))
    }
    assert daemon._is_real_keyboard(mock_kb) is True


def test_start_recording(daemon: HarpoDaemon) -> None:
    """
    Verifies transition to RECORDING state.
    """
    daemon.audio_streamer = MagicMock()
    daemon.console = MagicMock()
    daemon._notify = MagicMock()

    daemon._start_recording()

    assert daemon.state == DaemonState.RECORDING
    daemon.audio_streamer.start_recording.assert_called_once()
    daemon._notify.assert_called_once()


@pytest.mark.asyncio
async def test_stop_recording_no_data(daemon: HarpoDaemon) -> None:
    """
    Verifies transition back to IDLE when no audio data is captured.
    """
    daemon.state = DaemonState.RECORDING
    daemon.audio_streamer = MagicMock()
    daemon.audio_streamer.stop_recording.return_value = np.array([], dtype=np.float32)
    daemon.console = MagicMock()
    daemon._notify = MagicMock()

    await daemon._stop_recording()

    assert daemon.state == DaemonState.IDLE
    daemon.audio_streamer.stop_recording.assert_called_once()
