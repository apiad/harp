"""
Tests for the Harp daemon.
"""

from harp.daemon import DaemonState, HarpoDaemon


def test_daemon_initial_state() -> None:
    """
    Checks if the HarpoDaemon initializes in IDLE state.
    """
    daemon = HarpoDaemon()
    assert daemon.state == DaemonState.IDLE
