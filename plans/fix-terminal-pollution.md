# Implementation Plan: Terminal Pollution Fix (uinput Interceptor)

This plan outlines the steps to fix the `^@` terminal pollution issue by implementing a robust "interceptor" using `evdev.grab()` and `uinput` passthrough.

## Phase 1: CLI and Configuration
- [ ] Update `src/harp/__main__.py` to accept a `--device` / `-d` option for selecting a specific input device.
- [ ] Pass the device selection to `HarpDaemon`.

## Phase 2: Interceptor Core (`src/harp/daemon.py`)
- [ ] **Device Selection Logic**: Update `_main_loop` to filter devices based on name or path if provided.
- [ ] **Keyboard Grabbing**:
    - Implement `device.grab()` for selected keyboard devices.
    - Wrap in `try/except PermissionError` with clear instructions for the `input` group.
    - Ensure `device.ungrab()` is called in a `finally` block or upon `KeyboardInterrupt`.
- [ ] **Virtual Keyboard (uinput)**:
    - Initialize a `uinput.Device` that mirrors the capabilities of the grabbed physical devices.
    - Handle `uinput` permission errors (e.g., `/dev/uinput` access).
- [ ] **Event Passthrough and Suppression**:
    - Modify `_handle_events` to re-emit all captured events to the `uinput.Device` using `device.emit()`.
    - Specifically **suppress** the `Ctrl+Space` hotkey events so they are not re-emitted to the system.
    - Maintain state for `_suppressed_keys` to ensure "up" events for the hotkey are also consumed.

## Phase 3: Validation and User Experience
- [ ] **Error Messaging**: Provide helpful commands (e.g., `sudo usermod -aG input $USER`) when permissions are missing.
- [ ] **Manual Testing**:
    - Verify `uv run harp` no longer prints `^@` when `Ctrl+Space` is pressed.
    - Confirm all other keyboard input (typing, shortcuts) works normally in other applications while the daemon is running.
    - Verify the keyboard is correctly released when the daemon is stopped.

## Technical Details
- **Exclusive Access**: `device.grab()` prevents the kernel from passing events to other listeners (including the terminal).
- **Event Re-emission**: Using `uinput` ensures that the daemon acts as a transparent proxy for all non-hotkey input.
- **Cleanup**: It is critical to `ungrab()` the device to avoid locking the user out of their keyboard if the daemon crashes.
