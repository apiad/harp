"""Rich Live panel display for a HarpSession's events."""

from __future__ import annotations

from typing import Callable, Iterator, Optional

from rich.console import Console
from rich.panel import Panel

from harp.events import CommitEvent


class _RenderedPanel(Panel):
    """Panel subclass whose ``str()`` renders to a plain-text frame.

    Tests assert text content via ``str(panel)``; the default
    ``Panel.__str__`` returns only the object repr.
    """

    def __str__(self) -> str:  # type: ignore[override]
        console = Console(record=True, width=80, file=None)
        with console.capture() as capture:
            console.print(self)
        return capture.get()


class TerminalDisplay:
    """Renders a HarpSession's commit events as a Rich panel.

    ``consume()`` blocks the calling thread, pulling events from the
    iterator and updating the panel. If ``on_frame`` is provided, each
    rendered panel is also passed to it (used by tests).
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        on_frame: Optional[Callable[[Panel], None]] = None,
    ) -> None:
        self._console = console or Console()
        self._on_frame = on_frame
        self.last_text: str = ""

    def render(self, event: Optional[CommitEvent]) -> Panel:
        if event is None:
            body = "[dim](listening…)[/]"
            footer = ""
        else:
            body = f"[italic green]{event.text}[/]"
            footer = f"[dim]listening… {event.words} words[/]"
        return _RenderedPanel(body, title="[bold cyan]Harp[/]", subtitle=footer, border_style="cyan")

    def consume(self, events: Iterator[CommitEvent]) -> None:
        from rich.live import Live

        with Live(self.render(None), console=self._console, refresh_per_second=10) as live:
            for ev in events:
                self.last_text = ev.text
                frame = self.render(ev)
                live.update(frame)
                if self._on_frame is not None:
                    self._on_frame(frame)

    def print_final(self, text: str) -> None:
        if not text:
            self._console.print("[dim](empty session)[/]")
            return
        self._console.print(Panel(f"[italic green]{text}[/]", title="[bold cyan]Final[/]", border_style="cyan"))
