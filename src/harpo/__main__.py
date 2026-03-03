"""
CLI entry point for Harpo.
"""

import typer

from harpo.daemon import HarpoDaemon

app = typer.Typer()


@app.command()
def start() -> None:
    """
    Starts the Harpo background daemon.
    """
    daemon = HarpoDaemon()
    daemon.run()


if __name__ == "__main__":
    app()
