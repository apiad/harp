"""
CLI entry point for Harp.
"""

import shutil
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from harp.config import find_config_file, load_config

app = typer.Typer(help="Harp: A Wayland daemon for voice transcription and commands.")
models_app = typer.Typer(help="Manage local Whisper models.")
app.add_typer(models_app, name="models")

console = Console()


@app.command()
def start(
    device: Optional[str] = typer.Option(
        None, "--device", "-d", help="Path or name of the device to grab"
    ),
    toggle: Optional[bool] = typer.Option(
        None, "--toggle", "-t", help="Toggle recording state on keypress"
    ),
    full: Optional[bool] = typer.Option(
        None, "--full", "-f", help="Type all characters including symbols (opt-in)"
    ),
    type_result: Optional[bool] = typer.Option(
        None, "--type", help="Type the transcription result"
    ),
    copy_result: Optional[bool] = typer.Option(
        None, "--copy", help="Copy the transcription result to the clipboard"
    ),
    send_clipboard: Optional[int] = typer.Option(
        None,
        "--send-clipboard",
        help="Tokens to send from clipboard context in command mode",
    ),
    transcribe_prompt: Optional[str] = typer.Option(
        None, "--transcribe-prompt", help="Custom prompt for transcription"
    ),
    command_prompt: Optional[str] = typer.Option(
        None, "--command-prompt", help="Custom prompt for command mode"
    ),
) -> None:
    """
    Starts the Harp background daemon.
    """
    # Create overrides dict from CLI options (excluding None values)
    overrides = {
        "device": device,
        "toggle": toggle,
        "full_mode": full,
        "type": type_result,
        "copy": copy_result,
        "send_clipboard": send_clipboard,
        "transcribe_prompt": transcribe_prompt,
        "command_prompt": command_prompt,
    }

    config = load_config(overrides=overrides)

    from harp.daemon import HarpDaemon
    from harp.whisper import LocalWhisperEngine

    # Pre-flight check: Verify if local model is downloaded
    local_models = LocalWhisperEngine.list_local_models()
    # faster-whisper model names in cache usually include 'models--' prefix or are just the size
    # Let's check for exact match or partial match
    model_found = False
    for m in local_models:
        if config.local_model in m:
            model_found = True
            break

    if not model_found:
        console.print(
            f"[bold red]Error:[/] Whisper model '[bold cyan]{config.local_model}[/]' not found."
        )
        console.print(
            f"Please run: [bold green]harp models download {config.local_model}[/]"
        )
        raise typer.Exit(code=1)

    daemon = HarpDaemon(config=config)
    daemon.run()


@models_app.command("download")
def models_download(
    model: str = typer.Argument(
        "base", help="Model size to download (tiny, base, small, medium, large-v3)"
    ),
) -> None:
    """
    Downloads a Whisper model for local transcription.
    """
    from harp.whisper import LocalWhisperEngine

    console.print(f"Downloading Whisper model '[bold cyan]{model}[/]'...")
    try:
        path = LocalWhisperEngine.download(model)
        console.print(f"[bold green]Successfully downloaded model to:[/] {path}")
    except Exception as e:
        console.print(f"[bold red]Error downloading model:[/] {e}")
        raise typer.Exit(code=1)


@models_app.command("list")
def models_list() -> None:
    """
    Lists locally available Whisper models.
    """
    from harp.whisper import LocalWhisperEngine

    models = LocalWhisperEngine.list_local_models()
    if not models:
        console.print("[yellow]No local models found.[/]")
        return

    table = Table(title="Local Whisper Models")
    table.add_column("Model Name", style="cyan")
    table.add_column("Location", style="dim")

    root = Path.home() / ".cache" / "harp" / "models"
    for m in models:
        table.add_row(m, str(root / m))

    console.print(table)


@models_app.command("remove")
def models_remove(
    model: str = typer.Argument(..., help="Model name or size to remove"),
) -> None:
    """
    Removes a locally cached Whisper model.
    """
    root = Path.home() / ".cache" / "harp" / "models"
    model_path = root / model

    # Try exact match first, then partial
    if not model_path.exists():
        for d in root.iterdir():
            if model in d.name:
                model_path = d
                break

    if not model_path.exists() or not model_path.is_dir():
        console.print(
            f"[bold red]Error:[/] Model '[bold cyan]{model}[/]' not found in {root}"
        )
        raise typer.Exit(code=1)

    if typer.confirm(
        f"Are you sure you want to remove model '[bold cyan]{model_path.name}[/]'?"
    ):
        try:
            shutil.rmtree(model_path)
            console.print(f"[bold green]Removed model:[/] {model_path.name}")
        except Exception as e:
            console.print(f"[bold red]Error removing model:[/] {e}")
            raise typer.Exit(code=1)


@app.command()
def config() -> None:
    """
    Shows the currently resolved configuration.
    """
    config_path = find_config_file()
    if config_path:
        console.print(f"[bold green]Resolved configuration from:[/] {config_path}")
    else:
        console.print("[bold yellow]No .harp.yaml found. Using defaults/env.[/]")

    resolved_config = load_config()
    config_dict = resolved_config.model_dump(by_alias=True)

    yaml_str = yaml.dump(config_dict, sort_keys=False)
    syntax = Syntax(yaml_str, "yaml", theme="monokai", line_numbers=True)
    console.print(syntax)


@app.command()
def init() -> None:
    """
    Creates a default .harp.yaml in the current directory.
    """
    config_path = Path(".harp.yaml")
    if config_path.exists():
        console.print(f"[bold red]Error:[/] {config_path} already exists.")
        raise typer.Exit(code=1)

    from harp.config import HarpConfig

    default_config = HarpConfig().model_dump(by_alias=True)

    try:
        with open(config_path, "w") as f:
            yaml.dump(default_config, f, sort_keys=False)
        console.print(f"[bold green]Created default configuration at:[/] {config_path}")
    except Exception as e:
        console.print(f"[bold red]Error creating configuration:[/] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
