# RCA Report: Keyboard Emulation Issues (Ghost Modifiers & Missing Characters)

## Symptom
1.  **Ghost Modifiers**: The system behaves as if the `Ctrl` key is held down after triggering transcription. This causes unintended side effects like closing windows (`Ctrl+W`) or opening new ones (`Ctrl+N`) while the daemon is typing.
2.  **Missing Spanish Characters**: Transcription text containing tildes or Spanish-specific characters (e.g., `á`, `é`, `ñ`) are not typed into the active window.

## Context
- **Files involved**: `src/harp/daemon.py` (modifier logic) and `src/harp/input.py` (character mapping).
- **Mechanism**: `evdev` grabs physical keyboards; a virtual `uinput` device proxies non-hotkey events and types transcription results.

## Root Cause Analysis

### 1. Ghost Modifiers (Stuck Ctrl)
The `HarpoDaemon._handle_events` logic uses a suppression list (`_suppressed_keys`) to hide the hotkey from the system.
- When the user presses `Ctrl`, it is **emitted** to the system because the hotkey isn't yet confirmed (Space is still up).
- Once `Space` is pressed, the hotkey is confirmed, and both `Ctrl` and `Space` are added to `_suppressed_keys`.
- When the user releases `Ctrl`, the "Up" event is **suppressed**.
- **Result**: The OS receives a `KEY_DOWN` for `Ctrl` but never a `KEY_UP`. It remains logically "stuck" in the pressed state.

### 2. Missing Spanish Characters
The `WaylandTyper` uses a static `_key_map` that only includes basic US-ASCII characters.
- Characters like `á` or `ñ` do not exist in the map.
- The `type_text` method explicitly prints a warning and skips any character not found in the map.
- **Result**: Non-ASCII characters are lost during the typing phase.

## Proposed Fix Strategy

### Fix for Ghost Modifiers:
- Immediately after adding a modifier to `_suppressed_keys` upon hotkey confirmation, the daemon must emit a virtual `KEY_UP` event for that modifier to the passthrough device. This "cancels" the initial `KEY_DOWN` that was allowed to leak.

### Fix for Spanish Characters:
- Expand `WaylandTyper` to support common Spanish characters.
- **Approach**: For the MVP, we can add a secondary mapping for common accented characters using standard dead-key combinations or scancodes typical of Latin/International layouts. Alternatively, implement the `Ctrl+Shift+U` Unicode entry sequence which is supported by most Linux environments.

---
*Status: Root Cause Identified. Ready for Planning phase.*
