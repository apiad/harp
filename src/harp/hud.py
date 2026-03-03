"""
Fallback HUD using desktop notifications (notify-send).
"""

import subprocess


class HarpoHUD:
    """
    A fallback HUD that uses system notifications to display interim text.
    """

    def __init__(self) -> None:
        """
        Initializes the notification-based HUD.
        """
        self._is_visible = False
        # Use a consistent ID or tag if supported, though notify-send behavior varies.
        # On some systems, we can use -p to get an ID and then replace it.
        self._notif_id = None

    def update_text(self, text: str) -> None:
        """
        Updates the notification with new interim text.
        """
        if not self._is_visible or not text:
            return

        # We use a short timeout so it doesn't stay forever.
        # On many systems, --replace-id (or similar) is not standard across all notify-send versions.
        # A common trick to avoid flooding is to use a fixed summary.
        cmd = [
            "notify-send",
            "Harp (Interim)",
            text,
            "-t",
            "2000",
            "-h",
            "string:x-canonical-private-synchronous:harp-interim",
        ]
        try:
            subprocess.run(cmd, check=False)
        except Exception:
            pass

    def show(self) -> None:
        """
        Enables the HUD.
        """
        self._is_visible = True

    def hide(self) -> None:
        """
        Hides the HUD by sending a clear/empty notification or just stopping updates.
        """
        self._is_visible = False
        # Optional: send a 'transcription finished' notification or just let it expire.

    def stop(self) -> None:
        """
        Cleanup.
        """
        self.hide()
