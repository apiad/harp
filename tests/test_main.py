"""
Tests for the CLI entry point.
"""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from harp.__main__ import app

runner = CliRunner()


@patch("harp.__main__.HarpDaemon")
@patch("harp.__main__.load_config")
def test_cli_start_defaults(
    mock_load_config: MagicMock, mock_daemon_class: MagicMock
) -> None:
    """
    Verifies the start command with default values.
    """
    mock_instance = mock_daemon_class.return_value
    mock_config = MagicMock()
    mock_load_config.return_value = mock_config

    result = runner.invoke(app, ["start"])

    assert result.exit_code == 0
    # verify that load_config was called with CLI overrides (all None or defaults)
    mock_load_config.assert_called_once()
    # verify that HarpDaemon was called with the resolved config
    mock_daemon_class.assert_called_once_with(config=mock_config)
    mock_instance.run.assert_called_once()


@patch("harp.__main__.HarpDaemon")
@patch("harp.__main__.load_config")
def test_cli_start_custom(
    mock_load_config: MagicMock, mock_daemon_class: MagicMock
) -> None:
    """
    Verifies the start command with custom flags.
    """
    mock_instance = mock_daemon_class.return_value
    mock_config = MagicMock()
    mock_load_config.return_value = mock_config

    result = runner.invoke(
        app,
        [
            "start",
            "--device",
            "/dev/input/event0",
            "--toggle",
            "--full",
            "--type",
            "--copy",
            "--send-clipboard",
            "1000",
        ],
    )

    assert result.exit_code == 0
    # Verify overrides passed to load_config
    args, kwargs = mock_load_config.call_args
    overrides = kwargs["overrides"]
    assert overrides["device"] == "/dev/input/event0"
    assert overrides["toggle"] is True
    assert overrides["full_mode"] is True
    assert overrides["type"] is True
    assert overrides["copy"] is True
    assert overrides["send_clipboard"] == 1000

    mock_daemon_class.assert_called_once_with(config=mock_config)
    mock_instance.run.assert_called_once()


def test_cli_config_command() -> None:
    """
    Verifies the config command.
    """
    with patch("harp.__main__.load_config") as mock_load:
        mock_config = MagicMock()
        mock_config.model_dump.return_value = {"api_key": "test"}
        mock_load.return_value = mock_config

        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "api_key: test" in result.output


def test_cli_init_command() -> None:
    """
    Verifies the init command creates a file.
    """
    from pathlib import Path
    import os

    config_path = Path(".harp.yaml")
    if config_path.exists():
        os.remove(config_path)

    try:
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert config_path.exists()
    finally:
        if config_path.exists():
            os.remove(config_path)
