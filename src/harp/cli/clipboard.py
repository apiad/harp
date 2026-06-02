"""Clipboard-based delivery of finalized transcriptions."""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Callable, Optional


def _default_snapshot() -> bytes:
    result = subprocess.run(
        ["wl-paste", "--no-newline"],
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else b""


def _default_write(payload: bytes) -> None:
    if payload:
        subprocess.run(["wl-copy"], input=payload, check=False)
    else:
        subprocess.run(["wl-copy", "--clear"], check=False)


class ClipboardSink:
    """Delivers ``text`` via the system clipboard and optionally a Ctrl+V.

    The four-step dance: snapshot existing clipboard → write payload →
    synthesize Ctrl+V (if ``paste``) → wait → restore snapshot.

    Constructor injection points (``snapshot``, ``write``, ``ctrl_v``,
    ``sleep``) exist for tests; the defaults shell out to ``wl-paste`` and
    ``wl-copy`` and call ``ctrl_v_fallback`` which is set by the CLI
    wiring (Task 8) to the WaylandTyper Ctrl+V emitter.
    """

    def __init__(
        self,
        ctrl_v: Callable[[], None],
        snapshot: Optional[Callable[[], bytes]] = None,
        write: Optional[Callable[[bytes], None]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        paste: bool = True,
        post_paste_wait: float = 0.2,
    ) -> None:
        self._snapshot = snapshot or _default_snapshot
        self._write = write or _default_write
        self._ctrl_v = ctrl_v
        self._sleep = sleep or time.sleep
        self._paste = paste
        self._wait = post_paste_wait
        # When custom runners are injected (tests, alternative backends),
        # health depends only on those callables existing. Only validate
        # wl-copy/wl-paste presence when relying on the default shell-outs.
        using_defaults = snapshot is None or write is None
        if using_defaults:
            self.healthy = (
                shutil.which("wl-copy") is not None
                and shutil.which("wl-paste") is not None
            )
        else:
            self.healthy = True

    def deliver(self, text: str) -> None:
        if not text:
            return
        if not self.healthy:
            return  # warned at startup; nothing to do

        previous = self._snapshot()
        self._write(text.encode("utf-8"))
        if self._paste:
            self._ctrl_v()
            self._sleep(self._wait)
        self._write(previous)
