"""Tests for ClipboardSink."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from harp.cli.clipboard import ClipboardSink


@pytest.fixture()
def runner_double():
    """A double for the (wl_copy, wl_paste, ctrl_v, sleep) injection points."""
    return {
        "snapshot": MagicMock(return_value=b"PREEXISTING"),
        "write": MagicMock(),
        "ctrl_v": MagicMock(),
        "sleep": MagicMock(),
    }


def test_deliver_saves_writes_pastes_restores(runner_double) -> None:
    sink = ClipboardSink(
        snapshot=runner_double["snapshot"],
        write=runner_double["write"],
        ctrl_v=runner_double["ctrl_v"],
        sleep=runner_double["sleep"],
        paste=True,
    )

    sink.deliver("hello world")

    runner_double["snapshot"].assert_called_once_with()
    # Two writes: payload first, then restore.
    assert runner_double["write"].call_args_list == [
        call(b"hello world"),
        call(b"PREEXISTING"),
    ]
    runner_double["ctrl_v"].assert_called_once_with()
    runner_double["sleep"].assert_called_once()  # the 200ms after Ctrl+V


def test_deliver_with_no_paste_skips_keystroke(runner_double) -> None:
    sink = ClipboardSink(
        snapshot=runner_double["snapshot"],
        write=runner_double["write"],
        ctrl_v=runner_double["ctrl_v"],
        sleep=runner_double["sleep"],
        paste=False,
    )

    sink.deliver("hello")

    runner_double["ctrl_v"].assert_not_called()
    # Still saves and restores around the (skipped) paste.
    assert runner_double["write"].call_count == 2


def test_deliver_empty_text_is_a_noop(runner_double) -> None:
    sink = ClipboardSink(**{k: v for k, v in runner_double.items()}, paste=True)
    sink.deliver("")
    runner_double["snapshot"].assert_not_called()
    runner_double["write"].assert_not_called()
    runner_double["ctrl_v"].assert_not_called()


def test_deliver_handles_empty_initial_clipboard() -> None:
    snapshot = MagicMock(return_value=b"")
    write = MagicMock()
    ctrl_v = MagicMock()
    sleep = MagicMock()
    sink = ClipboardSink(snapshot=snapshot, write=write, ctrl_v=ctrl_v, sleep=sleep, paste=True)

    sink.deliver("X")

    # Restore call passes b"" → ClipboardSink decides to clear instead of write.
    # We assert at minimum: payload was written, no exception.
    assert write.call_args_list[0] == call(b"X")


def test_default_runners_use_wl_copy_and_wl_paste() -> None:
    """When constructed with no overrides, the default runners shell out."""
    with patch("harp.cli.clipboard.subprocess") as sp, patch(
        "harp.cli.clipboard.shutil.which", return_value="/usr/bin/wl-copy"
    ):
        sp.run.return_value.stdout = b"PRE"
        sp.run.return_value.returncode = 0
        sink = ClipboardSink(ctrl_v=MagicMock(), paste=False)
        sink.deliver("payload")

    cmds = [c.args[0] for c in sp.run.call_args_list]
    # First call: wl-paste --no-newline (snapshot)
    assert cmds[0][:1] == ["wl-paste"]
    # Subsequent: at least one wl-copy invocation for the payload
    assert any(c[:1] == ["wl-copy"] for c in cmds[1:])


def test_unhealthy_when_wl_copy_missing() -> None:
    with patch("harp.cli.clipboard.shutil.which", side_effect=lambda name: None):
        sink = ClipboardSink(ctrl_v=MagicMock(), paste=True)
        assert sink.healthy is False
        # deliver() degrades gracefully — no exception, no ctrl+v.
        sink.deliver("X")
