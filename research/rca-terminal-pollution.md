# RCA Report: Terminal Pollution (^@) during Hotkey Press

## Symptom
When the `harp` daemon is running, pressing the global hotkey (**Ctrl+Space**) causes `^@` characters to be printed in the terminal output. These characters appear every time the hotkey is used to toggle between 'capturing' and 'idle' states.

## Context
- **Files involved:** `src/harp/daemon.py`
- **Technology:** `evdev` for input monitoring on Linux.
- **Environment:** Running `uv run harp` in a terminal emulator.

## Investigation Summary
1.  **Lack of Input Grabbing:** The `HarpDaemon` class initializes `evdev.InputDevice` objects but does not call `device.grab()`. This means that keyboard events are passed to both the daemon and the active application (the terminal).
2.  **Ctrl+Space Mapping:** In most Linux terminal emulators, the `Ctrl+Space` key combination is mapped to the ASCII NULL character (`\0`), which is visually represented as `^@`.

## Root Cause
The daemon lacks exclusive access to the input device because it does not "grab" it. As a result, when `Ctrl+Space` is pressed, the event is also received by the terminal where the daemon is running. The terminal interprets this combination as a NULL byte and prints `^@` to the console.

## Impact
- **Terminal Clutter:** The output is filled with `^@` characters.
- **Application Interference:** Any application active while the hotkey is pressed will receive the `Ctrl+Space` input, which may trigger unexpected internal shortcuts (e.g., "Set Mark" in Emacs).

## Proposed Fix Strategy
A robust fix involves:
1.  **Grabbing the Keyboard:** Call `device.grab()` to gain exclusive access to input events.
2.  **Using uinput for Passthrough:** Re-emit all captured keys (except the hotkey) back to the system via `uinput` so other applications continue to function normally.
3.  **Hotkey Suppression:** Do not re-emit the `Ctrl+Space` combination, effectively "consuming" the hotkey.

---
*Status: Root Cause Identified. Ready for Planning phase.*
