"""Tests for harp.events."""

from harp.events import CommitEvent


def test_commit_event_is_frozen_dataclass():
    ev = CommitEvent(text="hello world", words=2, ts=1.5)
    assert ev.text == "hello world"
    assert ev.words == 2
    assert ev.ts == 1.5

    try:
        ev.text = "mutated"  # type: ignore[misc]
    except Exception as exc:
        assert "frozen" in str(exc).lower() or "FrozenInstanceError" in type(exc).__name__
    else:
        raise AssertionError("CommitEvent should be frozen")


def test_commit_event_words_matches_text_split():
    """Convention check: callers compute words = len(text.split()); CommitEvent stores it as-given."""
    ev = CommitEvent(text="one two three", words=3, ts=0.0)
    assert ev.words == len(ev.text.split())
