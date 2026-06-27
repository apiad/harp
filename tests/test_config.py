"""Tests for harp.config streaming fields."""

from harp.config import HarpConfig


def test_streaming_defaults():
    c = HarpConfig()
    assert c.stream_warmup == 10.0
    assert c.stream_silence_threshold == 0.5
    assert c.stream_max_segment == 25.0
    assert c.stream_vad is True
    assert c.stream_transient is False
    assert c.stream_beam_size == 1


def test_old_window_fields_removed():
    c = HarpConfig()
    assert not hasattr(c, "stream_window")
    assert not hasattr(c, "stream_overlap")
