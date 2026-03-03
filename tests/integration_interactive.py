"""
Integration tests for the interactive transcription stitching logic.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
import pytest

from harp.daemon import DaemonState, HarpoDaemon
from harp.api import BatchResponse


@pytest.fixture
def interactive_daemon() -> HarpoDaemon:
    with (
        patch("harp.daemon.AudioStreamer"),
        patch("harp.daemon.WaylandTyper"),
        patch("harp.daemon.OpenRouterClient"),
        patch("harp.daemon.HarpoConfig"),
        patch("harp.daemon.HarpoHUD"),
    ):
        daemon = HarpoDaemon(interactive=True)
        daemon.console = MagicMock()
        return daemon


@pytest.mark.asyncio
async def test_stitching_overlap(interactive_daemon: HarpoDaemon) -> None:
    """
    Verifies that overlapping windows are stitched correctly without duplication.
    """
    daemon = interactive_daemon
    daemon.state = DaemonState.RECORDING
    daemon.interval = 0.001

    # Iteration 1: "The quick brown"
    daemon.audio_streamer.get_rolling_window.return_value = np.array([[0.1]])
    daemon.api_client.transcribe = AsyncMock(
        side_effect=[
            BatchResponse(full_text="The quick brown"),
            BatchResponse(full_text="brown fox jumps"),
            BatchResponse(full_text="fox jumps over"),
        ]
    )
    daemon.typer.filter_text.side_effect = lambda x: x

    task = asyncio.create_task(daemon._interactive_loop())

    # Run 3 iterations
    while daemon.api_client.transcribe.call_count < 3:
        await asyncio.sleep(0.001)

    daemon.state = DaemonState.IDLE
    await task

    # Expected sequence:
    # 1. "The quick brown"
    # 2. "The quick brown" + "fox jumps" -> "The quick brown fox jumps"
    # 3. "The quick brown fox jumps" + "over" -> "The quick brown fox jumps over"

    assert daemon.current_session_text == "The quick brown fox jumps over"
    # Verify type_diff was called with correct arguments
    daemon.typer.type_diff.assert_any_call(
        "The quick brown", "The quick brown fox jumps"
    )
    daemon.typer.type_diff.assert_any_call(
        "The quick brown fox jumps", "The quick brown fox jumps over"
    )


@pytest.mark.asyncio
async def test_stitching_no_overlap(interactive_daemon: HarpoDaemon) -> None:
    """
    Verifies that non-overlapping windows are appended.
    """
    daemon = interactive_daemon
    daemon.state = DaemonState.RECORDING
    daemon.interval = 0.001

    daemon.audio_streamer.get_rolling_window.return_value = np.array([[0.1]])
    daemon.api_client.transcribe = AsyncMock(
        side_effect=[
            BatchResponse(full_text="Part one"),
            BatchResponse(full_text="Part two"),
        ]
    )
    daemon.typer.filter_text.side_effect = lambda x: x

    task = asyncio.create_task(daemon._interactive_loop())

    while daemon.api_client.transcribe.call_count < 2:
        await asyncio.sleep(0.001)

    daemon.state = DaemonState.IDLE
    await task

    assert daemon.current_session_text == "Part one Part two"
