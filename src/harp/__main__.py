"""
CLI entry point for Harp.
"""

from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.syntax import Syntax

from harp.config import find_config_file, load_config
from harp.daemon import HarpDaemon

app = typer.Typer(help="Harp: A Wayland daemon for voice transcription and commands.")
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
    daemon = HarpDaemon(config=config)
    daemon.run()


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
    # Convert to dict for display, using aliases to match .harp.yaml keys
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

    # Use defaults from HarpConfig
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
