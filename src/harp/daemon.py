"""
Core logic for managing states and the background daemon loop.
"""

import asyncio
from enum import Enum, auto


class DaemonState(Enum):
    """
    Possible states for the Harpo daemon.
    """

    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()


class HarpoDaemon:
    """
    Manages the lifecycle of the Harpo daemon.
    """

    def __init__(self) -> None:
        """
        Initializes the HarpoDaemon with its components and state.
        """
        self.state: DaemonState = DaemonState.IDLE

    async def _main_loop(self) -> None:
        """
        The asynchronous main loop of the daemon.
        """
        # Placeholder for DBus-based global shortcut handling
        while True:
            await asyncio.sleep(1)

    def run(self) -> None:
        """
        Entry point to start the asynchronous event loop.
        """
        asyncio.run(self._main_loop())
