"""Public event types yielded by HarpSession."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptEvent:
    """Two-tier transcription snapshot.

    ``committed`` is the cumulative finalized text: append-only, never revised.
    ``transient`` is the current hypothesis of the in-progress segment; it may
    be rewritten or emptied between events. Consumers render committed text
    "in the dark" and transient "in the light".
    """

    committed: str
    transient: str
    is_final: bool
    ts: float

    @property
    def text(self) -> str:
        return f"{self.committed} {self.transient}".strip()

    @property
    def words(self) -> int:
        return len(self.text.split())
