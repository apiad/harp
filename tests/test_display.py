"""Tests for TerminalDisplay."""

from __future__ import annotations

from typing import List

from harp.events import TranscriptEvent
from harp.cli.display import TerminalDisplay


def _ev(text: str, ts: float = 0.0) -> TranscriptEvent:
    return TranscriptEvent(committed=text, transient="", is_final=False, ts=ts)


def test_render_returns_panel_with_current_text() -> None:
    d = TerminalDisplay()
    panel = d.render(_ev("hello world", ts=0.5))
    # Renderable smoke-test: stringifies without exploding.
    s = str(panel)
    assert "hello world" in s
    assert "2" in s  # word count in the footer


def test_render_for_empty_session() -> None:
    d = TerminalDisplay()
    panel = d.render(None)
    s = str(panel)
    assert "listening" in s.lower() or "..." in s


def test_consume_records_each_event() -> None:
    """Drive consume() against a synthetic event stream and capture frames."""
    frames: List[str] = []
    d = TerminalDisplay(on_frame=lambda r: frames.append(str(r)))
    events = [
        _ev("hello", ts=0.1),
        _ev("hello world", ts=0.5),
    ]
    d.consume(iter(events))
    assert any("hello" in f for f in frames)
    assert any("hello world" in f for f in frames)
