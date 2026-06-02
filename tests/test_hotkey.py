"""Tests for the hotkey state machine."""

from __future__ import annotations

from harp.cli.hotkey import HotkeyAction, HotkeyStateMachine, KeyEvent


def kd(code: int) -> KeyEvent:
    return KeyEvent(code=code, down=True)


def ku(code: int) -> KeyEvent:
    return KeyEvent(code=code, down=False)


CTRL = 29  # KEY_LEFTCTRL
SPACE = 57  # KEY_SPACE


def test_hold_mode_starts_on_ctrl_space_down_and_stops_on_release() -> None:
    m = HotkeyStateMachine(toggle=False)
    assert m.handle(kd(CTRL)) is None
    assert m.handle(kd(SPACE)) == HotkeyAction.START
    assert m.handle(ku(SPACE)) == HotkeyAction.STOP
    assert m.handle(ku(CTRL)) is None


def test_hold_mode_stops_when_ctrl_released_first() -> None:
    m = HotkeyStateMachine(toggle=False)
    m.handle(kd(CTRL))
    assert m.handle(kd(SPACE)) == HotkeyAction.START
    assert m.handle(ku(CTRL)) == HotkeyAction.STOP


def test_toggle_mode_first_press_starts_second_press_stops() -> None:
    m = HotkeyStateMachine(toggle=True)
    m.handle(kd(CTRL))
    assert m.handle(kd(SPACE)) == HotkeyAction.START
    # Releases do nothing in toggle mode.
    assert m.handle(ku(SPACE)) is None
    assert m.handle(ku(CTRL)) is None
    # Second hit toggles off.
    m.handle(kd(CTRL))
    assert m.handle(kd(SPACE)) == HotkeyAction.STOP


def test_unrelated_keys_ignored() -> None:
    m = HotkeyStateMachine(toggle=False)
    assert m.handle(kd(30)) is None
    assert m.handle(ku(30)) is None
