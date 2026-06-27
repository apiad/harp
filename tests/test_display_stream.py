"""Tests for streaming dark/dim line rendering."""

from harp.cli.display import render_line
from harp.events import TranscriptEvent


def test_render_line_marks_committed_and_transient():
    ev = TranscriptEvent(
        committed="hello world", transient="how are", is_final=False, ts=1.0
    )
    out = render_line(ev)
    assert "hello world" in out
    assert "how are" in out
    assert "[dim]" in out


def test_render_line_final_has_no_transient_markup():
    ev = TranscriptEvent(
        committed="hello world", transient="", is_final=True, ts=2.0
    )
    out = render_line(ev)
    assert out == "hello world"
    assert "[dim]" not in out
