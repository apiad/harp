# Implementation Plan: Keyboard Emulation

This plan outlines the steps to implement keyboard emulation for `harp`, allowing transcribed text to be typed directly into the active window via `uinput`.

## Phase 1: Core Typing Implementation (`src/harp/input.py`)
- [ ] **Implement `WaylandTyper`**:
    - [ ] Initialize a `uinput.Device` with standard US keys (A-Z, 0-9, common punctuation, Space, Enter).
    - [ ] Create a mapping dictionary between characters and `uinput` key codes (including shift states).
    - [ ] Implement `type_text(text: str)`:
        - Iterate through characters.
        - Look up key and shift state.
        - Emit `KEY_LEFTSHIFT` if needed.
        - Emit character key down and up.
        - Release `KEY_LEFTSHIFT` if it was held.

## Phase 2: Daemon Integration and Error Handling (`src/harp/daemon.py`)
- [ ] **Integrate Typer**:
    - [ ] Initialize `WaylandTyper` in `HarpDaemon.__init__`.
    - [ ] Wrap the transcription and typing logic in `_stop_recording()` within a `try/except` block.
- [ ] **Robust Feedback**:
    - [ ] If transcription returns an error or `type_text` fails, call `self._notify("Error", error_message)`.
    - [ ] Ensure the daemon state resets to `IDLE` regardless of success or failure.
- [ ] **Recursive Prevention**: Update device discovery to exclude any device named "Harp Virtual Keyboard" to prevent the daemon from "hearing" its own typing.

## Phase 3: Validation and Testing
- [ ] **Manual Testing**:
    - [ ] Run `uv run harp`.
    - [ ] Record text including uppercase letters and punctuation (e.g., "Hello, World!").
    - [ ] Verify the text is typed correctly into a text editor.
- [ ] **Error Testing**:
    - [ ] Simulate an API failure (e.g., disconnect internet) and verify a notification appears without crashing the daemon.
    - [ ] Test with `/dev/uinput` permissions missing.

## Technical Details
- **uinput Shift Mapping**: Punctuation like `!` or `@` requires emulating a `LEFTSHIFT` press before the corresponding key (e.g., `1` or `2`).
- **Device Filtering**: It's crucial to filter out our own virtual device during discovery to avoid a feedback loop where the daemon tries to "process" the keys it just typed.
