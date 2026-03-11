# Implementation Plan: Initial MVP (Wayland/evdev)

This plan outlines the steps to implement a functional MVP for the `harp` background daemon. The MVP will listen for a global hotkey (Ctrl+Space) using `evdev`, providing both console and visual feedback.

## Phase 1: Dependency and Configuration
- [ ] Add `evdev` to `pyproject.toml` dependencies.
- [ ] Ensure the project script entry point is correctly configured in `pyproject.toml` so `uv run harp` works.
- [ ] (Manual Step) Ensure the user is in the `input` and `uinput` groups.

## Phase 2: Core Implementation (`src/harp/`)
- [ ] **Notification Helper**: Implement a `_notify` method in `HarpDaemon` using `subprocess` to call `notify-send`.
- [ ] **Input Listener**:
    - Implement a device discovery mechanism to find keyboard devices in `/dev/input/`.
    - Use `evdev.AsyncInputDevice` to listen for key events.
    - Track the state of `KEY_LEFTCTRL`, `KEY_RIGHTCTRL`, and `KEY_SPACE`.
- [ ] **State Logic**:
    - Trigger "capturing" (console + notification) when `Ctrl` is held and `Space` is pressed.
    - Trigger "idle" (console + notification) when both are released.

## Phase 3: Integration and Testing
- [ ] Update `src/harp/__main__.py` to correctly initialize and run the `HarpDaemon` within an `asyncio` loop.
- [ ] Test the daemon by running `uv run harp` and verifying both console output and desktop notifications.
- [ ] Handle permission errors (e.g., `PermissionError: [Errno 13] Permission denied: '/dev/input/eventX'`) gracefully with clear instructions for the user.

## Technical Details
- **AsyncIO Integration**: The `evdev` listener will run as an `asyncio` task alongside the main daemon loop.
- **Wayland Compatibility**: Since `evdev` reads directly from `/dev/input/`, it is agnostic of the Wayland compositor (KDE, GNOME, etc.), provided the user has the necessary permissions.
- **Feedback**:
    - `notify-send "Harp" "Capturing..." -t 1000`
    - `notify-send "Harp" "Idle" -t 1000`
