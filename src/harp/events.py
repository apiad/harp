"""Public event types yielded by HarpSession."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommitEvent:
    """A snapshot of the current committed transcription prefix.

    The full committed prefix is carried in ``text`` every time, so clients
    that need delta-awareness (e.g. a Rich Live panel that animates
    back-patches) compute deltas by diffing against the previous event's
    text. There is no separate "revision" event.
    """

    text: str
    words: int
    ts: float
