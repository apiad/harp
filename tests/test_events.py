"""Tests for harp.events."""

import dataclasses

import pytest

from harp.events import TranscriptEvent


def test_text_joins_committed_and_transient():
    ev = TranscriptEvent(
        committed="hello world", transient="how are", is_final=False, ts=1.0
    )
    assert ev.text == "hello world how are"


def test_text_strips_when_transient_empty():
    ev = TranscriptEvent(committed="hello world", transient="", is_final=True, ts=2.0)
    assert ev.text == "hello world"


def test_words_counts_full_text():
    ev = TranscriptEvent(committed="one two", transient="three", is_final=False, ts=0.0)
    assert ev.words == 3


def test_event_is_frozen():
    ev = TranscriptEvent(committed="a", transient="b", is_final=False, ts=0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.committed = "x"  # type: ignore[misc]


def test_public_api_importable() -> None:
    import harp

    assert hasattr(harp, "HarpSession")
    assert hasattr(harp, "DictationSession")
    assert hasattr(harp, "MicrophoneSource")
    assert hasattr(harp, "TranscriptEvent")
    assert hasattr(harp, "AudioSource")
    assert harp.__version__ == "0.10.0"
