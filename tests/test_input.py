"""
Tests for the WaylandTyper.
"""

from unittest.mock import MagicMock, patch

import pytest
import uinput

from harp.input import WaylandTyper


@pytest.fixture
def typer() -> WaylandTyper:
    """
    Provides a fresh WaylandTyper instance.
    """
    with patch("uinput.Device"):
        return WaylandTyper(full_mode=False)


def test_typer_initial_state(typer: WaylandTyper) -> None:
    """
    Verifies initial state and mode.
    """
    assert typer.full_mode is False
    assert typer.device is not None


@patch("uinput.Device", side_effect=OSError("Permission denied"))
def test_typer_init_error(mock_device: MagicMock) -> None:
    """
    Verifies error handling during initialization (covers lines 44-49).
    """
    typer_obj = WaylandTyper()
    assert typer_obj.device is None


def test_create_key_map(typer: WaylandTyper) -> None:
    """
    Verifies the character mapping contains standard keys.
    """
    key_map = typer._create_key_map()
    assert "a" in key_map
    assert key_map["a"] == (uinput.KEY_A, False)
    assert "A" in key_map
    assert key_map["A"] == (uinput.KEY_A, True)
    assert " " in key_map
    assert key_map[" "] == (uinput.KEY_SPACE, False)
    assert "1" in key_map
    assert key_map["1"] == (uinput.KEY_1, False)


def test_filter_text_safe_mode(typer: WaylandTyper) -> None:
    """
    Checks filtering in safe mode.
    """
    input_text = "Hello! (World) - ñíá."
    # Safe mode allows letters, numbers, spaces, dots, commas, slashes, parens, and latin chars
    # '!' and '-' should be filtered out
    expected = "Hello (World)  ñíá."
    assert typer.filter_text(input_text) == expected


def test_filter_text_full_mode(typer: WaylandTyper) -> None:
    """
    Checks filtering in full mode.
    """
    typer.full_mode = True
    input_text = "Hello! (World) - ñíá."
    # Full mode allows everything
    assert typer.filter_text(input_text) == input_text


def test_backspace(typer: WaylandTyper) -> None:
    """
    Verifies backspace emission.
    """
    typer.device.emit = MagicMock()
    typer.backspace(3)
    # Each backspace is 2 calls (down, up)
    assert typer.device.emit.call_count == 6


def test_backspace_no_device(typer: WaylandTyper) -> None:
    """
    Verifies backspace logic when device is missing (covers line 158).
    """
    typer.device = None
    # Should not raise
    typer.backspace(1)


@patch("time.sleep")
def test_type_text_basic(mock_sleep: MagicMock, typer: WaylandTyper) -> None:
    """
    Verifies basic text typing emission.
    """
    typer.device.emit = MagicMock()
    typer.type_text("aB")

    # 'a' -> KEY_A (down, up)
    # 'B' -> LEFTSHIFT (down), KEY_B (down, up), LEFTSHIFT (up)
    # Total = 2 + 4 = 6 calls
    assert typer.device.emit.call_count == 6


def test_type_text_no_device(typer: WaylandTyper) -> None:
    """
    Verifies type_text logic when device is missing (covers lines 173-174).
    """
    typer.device = None
    # Should not raise
    typer.type_text("abc")


@patch("harp.input.WaylandTyper._type_unicode")
def test_type_text_unicode_fallback(
    mock_type_unicode: MagicMock, typer: WaylandTyper
) -> None:
    """
    Verifies that unmapped characters trigger unicode entry.
    """
    typer.type_text("€")
    mock_type_unicode.assert_called_once_with("€")


@patch("harp.input.WaylandTyper._type_unicode", side_effect=Exception("uinput error"))
def test_type_text_unicode_error(
    mock_type_unicode: MagicMock, typer: WaylandTyper
) -> None:
    """
    Verifies error handling when unicode typing fails (covers lines 191-192).
    """
    # Should not raise, just print warning
    typer.type_text("€")


@patch("time.sleep")
def test_type_unicode_sequence(mock_sleep: MagicMock, typer: WaylandTyper) -> None:
    """
    Verifies the complex Unicode hex sequence emission.
    """
    typer.device.emit = MagicMock()
    # 'ñ' is U+00F1
    typer._type_unicode("ñ")

    # 1. Ctrl down, Shift down, U down, U up = 4
    # 2. hex digits '00f1' (4 * 2) = 8
    # 3. Release Shift+Ctrl (2 up) = 2
    # Total = 4 + 8 + 2 = 14 calls
    assert typer.device.emit.call_count == 14
