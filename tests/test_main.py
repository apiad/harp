"""
Tests for the CLI entry point.
"""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from harp.cli.main import app

runner = CliRunner()


def _patch_runtime(*, model: str = "base", models_present: bool = True):
    """
    Returns a context manager stack that mocks every runtime dependency the
    CLI's run_daemon touches so the tests don't actually spin up threads,
    evdev, sounddevice, or whisper.
    """

    class _Stack:
        def __enter__(self):
            self._patches = [
                patch("harp.cli.main.load_config"),
                patch("harp.whisper.LocalWhisperEngine"),
                patch("harp.input.WaylandTyper"),
                patch("harp.cli.clipboard.ClipboardSink"),
                patch("harp.cli.hotkey.HotkeyWatcher"),
            ]
            mocks = [p.start() for p in self._patches]
            (
                self.load_config,
                self.whisper_engine,
                self.wayland_typer,
                self.clipboard_sink,
                self.hotkey_watcher,
            ) = mocks

            mock_config = MagicMock()
            mock_config.local_model = model
            self.load_config.return_value = mock_config
            self.mock_config = mock_config

            self.whisper_engine.list_local_models.return_value = (
                [model] if models_present else []
            )

            sink_instance = self.clipboard_sink.return_value
            sink_instance.healthy = True

            watcher_instance = self.hotkey_watcher.return_value
            watcher_instance._thread = None
            return self

        def __exit__(self, *exc):
            for p in self._patches:
                p.stop()

    return _Stack()


def test_cli_start_defaults() -> None:
    """
    Verifies the start command with default values wires HotkeyWatcher.
    """
    with _patch_runtime() as rt:
        result = runner.invoke(app, ["start"])

    assert result.exit_code == 0, result.output
    rt.load_config.assert_called_once()
    rt.hotkey_watcher.assert_called_once()
    rt.hotkey_watcher.return_value.start.assert_called_once()
    assert "Harp ready." in result.output


def test_cli_start_model_not_found() -> None:
    """
    Verifies the start command fails if the model is not found.
    """
    with _patch_runtime(model="large", models_present=False) as rt:
        result = runner.invoke(app, ["start"])

    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "large" in result.output
    rt.hotkey_watcher.assert_not_called()


def test_cli_start_custom() -> None:
    """
    Verifies the start command with custom flags forwards overrides.
    """
    with _patch_runtime() as rt:
        result = runner.invoke(
            app,
            [
                "start",
                "--device",
                "/dev/input/event0",
                "--toggle",
                "--full",
                "--no-paste",
                "--local-device",
                "cpu",
                "--local-compute-type",
                "float32",
            ],
        )

    assert result.exit_code == 0, result.output
    args, kwargs = rt.load_config.call_args
    overrides = kwargs["overrides"]
    assert overrides["device"] == "/dev/input/event0"
    assert overrides["toggle"] is True
    assert overrides["full_mode"] is True
    assert overrides["paste"] is False
    assert overrides["local_device"] == "cpu"
    assert overrides["local_compute_type"] == "float32"
    rt.hotkey_watcher.assert_called_once()
    rt.hotkey_watcher.return_value.start.assert_called_once()


def test_cli_config_command() -> None:
    """
    Verifies the config command.
    """
    with patch("harp.cli.main.load_config") as mock_load:
        mock_config = MagicMock()
        mock_config.model_dump.return_value = {"stream_slide_interval": 1.0}
        mock_load.return_value = mock_config

        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "stream_slide_interval: 1.0" in result.output


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
