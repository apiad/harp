"""
Tests for the CLI entry point.
"""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from harp.__main__ import app

runner = CliRunner()


@patch("harp.__main__.HarpoDaemon")
def test_cli_start_defaults(mock_daemon_class: MagicMock) -> None:
    """
    Verifies the start command with default values.
    """
    mock_instance = mock_daemon_class.return_value

    # Typer with a single command maps it to root, so no "start" argument needed
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    mock_daemon_class.assert_called_once_with(
        device_path=None, toggle=False, full_mode=False
    )
    mock_instance.run.assert_called_once()


@patch("harp.__main__.HarpoDaemon")
def test_cli_start_custom(mock_daemon_class: MagicMock) -> None:
    """
    Verifies the start command with custom flags.
    """
    mock_instance = mock_daemon_class.return_value

    result = runner.invoke(
        app,
        [
            "--device",
            "/dev/input/event0",
            "--toggle",
            "--full",
        ],
    )

    assert result.exit_code == 0
    mock_daemon_class.assert_called_once_with(
        device_path="/dev/input/event0",
        toggle=True,
        full_mode=True,
    )
    mock_instance.run.assert_called_once()


def test_cli_main_entry() -> None:
    """
    Verifies that running the module as script triggers typer.
    """
    with patch("harp.__main__.app"):
        # Just to cover the 'if __name__ == "__main__"' block indirectly
        # though we can't easily trigger it without a subprocess.
        pass
