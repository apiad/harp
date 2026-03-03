"""
CLI entry point for Harp.
"""

import typer

from harp.daemon import HarpoDaemon

app = typer.Typer()


@app.command()
def start(
    device: str = typer.Option(
        None, "--device", "-d", help="Path or name of the device to grab"
    ),
    toggle: bool = typer.Option(
        False, "--toggle", "-t", help="Toggle recording state on keypress"
    ),
    full: bool = typer.Option(
        False, "--full", "-f", help="Type all characters including symbols (opt-in)"
    ),
) -> None:
    """
    Starts the Harp background daemon.
    """
    daemon = HarpoDaemon(device_path=device, toggle=toggle, full_mode=full)
    daemon.run()


if __name__ == "__main__":
    app()
