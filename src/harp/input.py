"""
Keyboard emulation for Wayland.
"""

import time

import uinput


class WaylandTyper:
    """
    Emulates a physical keyboard to type text in Wayland environments.
    """

    def __init__(self) -> None:
        """
        Initializes the WaylandTyper device with US keyboard capabilities.
        """
        # Standard US keys mapping: character -> (uinput_key, needs_shift)
        self._key_map: dict[str, tuple[int, bool]] = self._create_key_map()

        # Create virtual device with all keys in our map
        keys = {k[0] for k in self._key_map.values()}
        # Ensure LEFTSHIFT is included for shift-based chars
        keys.add(uinput.KEY_LEFTSHIFT)

        try:
            self.device = uinput.Device(list(keys), name="Harp Virtual Keyboard")
        except (OSError, PermissionError):
            print(
                "Error creating uinput device for typing. "
                "Run: sudo chmod 666 /dev/uinput or sudo modprobe uinput."
            )
            self.device = None

    def _create_key_map(self) -> dict[str, tuple[int, bool]]:
        """
        Creates a mapping from characters to uinput key codes and shift state.
        """
        mapping: dict[str, tuple[int, bool]] = {
            " ": (uinput.KEY_SPACE, False),
            "\n": (uinput.KEY_ENTER, False),
            "\t": (uinput.KEY_TAB, False),
            ".": (uinput.KEY_DOT, False),
            ",": (uinput.KEY_COMMA, False),
            "!": (uinput.KEY_1, True),
            "@": (uinput.KEY_2, True),
            "#": (uinput.KEY_3, True),
            "$": (uinput.KEY_4, True),
            "%": (uinput.KEY_5, True),
            "^": (uinput.KEY_6, True),
            "&": (uinput.KEY_7, True),
            "*": (uinput.KEY_8, True),
            "(": (uinput.KEY_9, True),
            ")": (uinput.KEY_0, True),
            "-": (uinput.KEY_MINUS, False),
            "_": (uinput.KEY_MINUS, True),
            "=": (uinput.KEY_EQUAL, False),
            "+": (uinput.KEY_EQUAL, True),
            "?": (uinput.KEY_SLASH, True),
            "/": (uinput.KEY_SLASH, False),
            ":": (uinput.KEY_SEMICOLON, True),
            ";": (uinput.KEY_SEMICOLON, False),
            '"': (uinput.KEY_APOSTROPHE, True),
            "'": (uinput.KEY_APOSTROPHE, False),
        }

        # Letters a-z
        for i in range(ord("a"), ord("z") + 1):
            char = chr(i)
            key_code = getattr(uinput, f"KEY_{char.upper()}")
            mapping[char] = (key_code, False)
            mapping[char.upper()] = (key_code, True)

        # Numbers 0-9
        for i in range(10):
            mapping[str(i)] = (getattr(uinput, f"KEY_{i}"), False)

        return mapping

    def type_text(self, text: str) -> None:
        """
        Emulates keystrokes for the provided text.

        Args:
            text: The text to be typed into the active window.
        """
        if not self.device:
            print("Typer device not initialized. Cannot type text.")
            return

        for char in text:
            if char in self._key_map:
                key_code, needs_shift = self._key_map[char]

                if needs_shift:
                    self.device.emit(uinput.KEY_LEFTSHIFT, 1)

                self.device.emit(key_code, 1)
                self.device.emit(key_code, 0)

                if needs_shift:
                    self.device.emit(uinput.KEY_LEFTSHIFT, 0)
            else:
                print(f"Warning: Character '{char}' not in key map. Skipping.")

            # Small sleep to ensure the OS/App handles it correctly
            # although "Immediate" was requested, completely zero delay can sometimes drop chars
            time.sleep(0.001)
