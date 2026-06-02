"""Re-export the CLI Typer app for `python -m harp`."""

from harp.cli.main import app

if __name__ == "__main__":
    app()
