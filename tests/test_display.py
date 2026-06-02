"""Tests for TerminalDisplay."""

from __future__ import annotations

from typing import List

from harp.events import CommitEvent
from harp.cli.display import TerminalDisplay


def test_render_returns_panel_with_current_text() -> None:
    d = TerminalDisplay()
    panel = d.render(CommitEvent(text="hello world", words=2, ts=0.5))
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
        CommitEvent(text="hello", words=1, ts=0.1),
        CommitEvent(text="hello world", words=2, ts=0.5),
    ]
    d.consume(iter(events))
    assert any("hello" in f for f in frames)
    assert any("hello world" in f for f in frames)
