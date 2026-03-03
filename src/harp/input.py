"""
Keyboard emulation for Wayland.
"""

import time

import uinput


class WaylandTyper:
    """
    Emulates a physical keyboard to type text in Wayland environments.
    """

    def __init__(self, full_mode: bool = False) -> None:
        """
        Initializes the WaylandTyper device with US keyboard capabilities.

        Args:
            full_mode: Whether to allow all characters or just a safe subset.
        """
        self.full_mode = full_mode
        # Standard US keys mapping: character -> (uinput_key, needs_shift)
        self._key_map: dict[str, tuple[int, bool]] = self._create_key_map()

        # Create virtual device with all keys in our map
        keys = {k[0] for k in self._key_map.values()}
        # Ensure additional keys for Unicode entry (Ctrl+Shift+U)
        keys.add(uinput.KEY_LEFTSHIFT)
        keys.add(uinput.KEY_LEFTCTRL)
        keys.add(uinput.KEY_U)
        keys.add(uinput.KEY_ENTER)
        keys.add(uinput.KEY_SPACE)

        # Keys for hex digits (0-9, a-f)
        for i in range(10):
            keys.add(getattr(uinput, f"KEY_{i}"))
        for char in "abcdef":
            keys.add(getattr(uinput, f"KEY_{char.upper()}"))

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
            "`": (uinput.KEY_GRAVE, False),
            "~": (uinput.KEY_GRAVE, True),
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

    def _type_unicode(self, char: str) -> None:
        """
        Types a character using the Linux Unicode sequence (Ctrl+Shift+U + hex + Enter).
        """
        hex_code = f"{ord(char):04x}"

        # Press Ctrl+Shift+U
        self.device.emit(uinput.KEY_LEFTCTRL, 1)
        self.device.emit(uinput.KEY_LEFTSHIFT, 1)
        self.device.emit(uinput.KEY_U, 1)
        self.device.emit(uinput.KEY_U, 0)
        self.device.emit(uinput.KEY_LEFTSHIFT, 0)
        self.device.emit(uinput.KEY_LEFTCTRL, 0)

        time.sleep(0.01)

        # Type hex digits
        for digit in hex_code:
            key_code = getattr(uinput, f"KEY_{digit.upper()}")
            self.device.emit(key_code, 1)
            self.device.emit(key_code, 0)
            time.sleep(0.001)

        # Confirm with Enter (fixes the extra spaces issue)
        self.device.emit(uinput.KEY_ENTER, 1)
        self.device.emit(uinput.KEY_ENTER, 0)
        time.sleep(0.01)

    def type_text(self, text: str) -> None:
        """
        Emulates keystrokes for the provided text.

        Args:
            text: The text to be typed into the active window.
        """
        if not self.device:
            print("Typer device not initialized. Cannot type text.")
            return

        safe_punctuation = " ,.\n\t"
        # Dead keys that require a space if the next char is not a vowel
        dead_keys = ["'", "`"]
        vowels = "aeiouAEIOU"

        for i, char in enumerate(text):
            is_latin = ord(char) > 127
            is_alphanumeric = char.isalnum()
            is_safe_punct = char in safe_punctuation

            # Filtering logic for non-full mode
            if not self.full_mode:
                if not (is_alphanumeric or is_safe_punct or is_latin):
                    continue

            if char in self._key_map:
                key_code, needs_shift = self._key_map[char]

                if needs_shift:
                    self.device.emit(uinput.KEY_LEFTSHIFT, 1)

                self.device.emit(key_code, 1)
                self.device.emit(key_code, 0)

                if needs_shift:
                    self.device.emit(uinput.KEY_LEFTSHIFT, 0)

                # Dead key logic: if it's a potential dead key, check the next char
                if char in dead_keys:
                    next_char = text[i + 1] if i + 1 < len(text) else ""
                    if next_char not in vowels:
                        # Send space to render the dead key
                        self.device.emit(uinput.KEY_SPACE, 1)
                        self.device.emit(uinput.KEY_SPACE, 0)
            else:
                try:
                    self._type_unicode(char)
                except Exception:
                    print(f"Warning: Character '{char}' could not be typed. Skipping.")

            time.sleep(0.001)
