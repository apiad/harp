"""
Tests for the CLI entry point.
"""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from harp.__main__ import app

runner = CliRunner()


@patch("harp.whisper.LocalWhisperEngine")
@patch("harp.daemon.HarpDaemon")
@patch("harp.__main__.load_config")
def test_cli_start_defaults(
    mock_load_config: MagicMock,
    mock_daemon_class: MagicMock,
    mock_whisper_engine: MagicMock,
) -> None:
    """
    Verifies the start command with default values.
    """
    mock_instance = mock_daemon_class.return_value
    mock_config = MagicMock()
    mock_config.local_model = "base"
    mock_load_config.return_value = mock_config

    # Mock model check
    mock_whisper_engine.list_local_models.return_value = ["base"]

    result = runner.invoke(app, ["start"])

    assert result.exit_code == 0
    mock_load_config.assert_called_once()
    mock_daemon_class.assert_called_once_with(config=mock_config)
    mock_instance.run.assert_called_once()


@patch("harp.whisper.LocalWhisperEngine")
@patch("harp.daemon.HarpDaemon")
@patch("harp.__main__.load_config")
def test_cli_start_model_not_found(
    mock_load_config: MagicMock,
    mock_daemon_class: MagicMock,
    mock_whisper_engine: MagicMock,
) -> None:
    """
    Verifies that the start command fails if the model is not found.
    """
    mock_config = MagicMock()
    mock_config.local_model = "large"
    mock_load_config.return_value = mock_config

    # Mock model check - empty list
    mock_whisper_engine.list_local_models.return_value = []

    result = runner.invoke(app, ["start"])

    assert result.exit_code == 1
    assert "Error: Whisper model 'large' not found." in result.output
    mock_daemon_class.assert_not_called()


@patch("harp.whisper.LocalWhisperEngine")
@patch("harp.daemon.HarpDaemon")
@patch("harp.__main__.load_config")
def test_cli_start_custom(
    mock_load_config: MagicMock,
    mock_daemon_class: MagicMock,
    mock_whisper_engine: MagicMock,
) -> None:
    """
    Verifies the start command with custom flags.
    """
    mock_instance = mock_daemon_class.return_value
    mock_config = MagicMock()
    mock_config.local_model = "base"
    mock_load_config.return_value = mock_config

    mock_whisper_engine.list_local_models.return_value = ["base"]

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
        mock_config.model_dump.return_value = {"llm_api_key": "test"}
        mock_load.return_value = mock_config

        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "llm_api_key: test" in result.output


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


@patch("harp.whisper.LocalWhisperEngine")
def test_cli_models_list(mock_whisper_engine: MagicMock) -> None:
    """
    Verifies the models list command.
    """
    mock_whisper_engine.list_local_models.return_value = ["base", "tiny"]

    result = runner.invoke(app, ["models", "list"])
    assert result.exit_code == 0
    assert "base" in result.output
    assert "tiny" in result.output


@patch("harp.whisper.LocalWhisperEngine")
def test_cli_models_download(mock_whisper_engine: MagicMock) -> None:
    """
    Verifies the models download command.
    """
    mock_whisper_engine.download.return_value = "/path/to/model"

    result = runner.invoke(app, ["models", "download", "base"])
    assert result.exit_code == 0
    assert "Successfully downloaded model" in result.output
    mock_whisper_engine.download.assert_called_once_with("base")
