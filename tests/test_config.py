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
    assert c.stream_overlap == 3.0


def test_old_window_field_removed():
    c = HarpConfig()
    assert not hasattr(c, "stream_window")
