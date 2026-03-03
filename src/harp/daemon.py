"""
Core logic for managing states and the background daemon loop.
"""

import asyncio
import subprocess
import time
import wave
from enum import Enum, auto
from pathlib import Path

import evdev
import numpy as np

from harp.audio import AudioStreamer


class DaemonState(Enum):
    """
    Possible states for the Harpo daemon.
    """

    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()


class HarpoDaemon:
    """
    Manages the lifecycle of the Harpo daemon.
    """

    def __init__(self, device_path: str | None = None, toggle: bool = False) -> None:
        """
        Initializes the HarpoDaemon with its components and state.

        Args:
            device_path: Optional path or name of the device to grab.
            toggle: Whether to toggle state on keypress.
        """
        self.device_path: str | None = device_path
        self.toggle: bool = toggle
        self.state: DaemonState = DaemonState.IDLE
        self._keys_pressed: set[int] = set()
        self._suppressed_keys: set[int] = set()
        self._uinput_device: evdev.UInput | None = None
        self._grabbed_devices: list[evdev.InputDevice] = []
        self.audio_streamer = AudioStreamer()

    def _notify(self, title: str, message: str) -> None:
        """
        Sends a desktop notification using notify-send.

        Args:
            title: The title of the notification.
            message: The message body of the notification.
        """
        subprocess.run(["notify-send", "Harp", f"{title}: {message}", "-t", "1000"])

    def _start_recording(self) -> None:
        """
        Transitions to RECORDING and starts audio capture.
        """
        if self.state == DaemonState.IDLE:
            self.state = DaemonState.RECORDING
            self.audio_streamer.start_recording()
            print("capturing")
            self._notify("Status", "capturing")

    def _stop_recording(self) -> None:
        """
        Transitions to IDLE, stops capture, and saves WAV.
        """
        if self.state == DaemonState.RECORDING:
            self.state = DaemonState.IDLE
            audio_data = self.audio_streamer.stop_recording()
            print("idle")
            self._notify("Status", "idle")
            if audio_data.size > 0:
                self._save_wav(audio_data)

    def _save_wav(self, audio_data: np.ndarray) -> None:
        """
        Saves the recorded audio to a WAV file in the home directory.

        Args:
            audio_data: The captured float32 PCM data.
        """
        timestamp = int(time.time())
        filename = Path.home() / f"harp_test_{timestamp}.wav"

        # Convert float32 [-1.0, 1.0] to int16
        audio_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)

        try:
            with wave.open(str(filename), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 2 bytes for int16
                wf.setframerate(self.audio_streamer.samplerate)
                wf.writeframes(audio_int16.tobytes())
            print(f"Saved recording to {filename}")
        except Exception as e:
            print(f"Error saving WAV file: {e}")

    def _toggle_state(self) -> None:
        """
        Toggles the daemon state between IDLE and RECORDING.
        """
        if self.state == DaemonState.IDLE:
            self._start_recording()
        else:
            self._stop_recording()

    async def _handle_events(self, device: evdev.InputDevice) -> None:
        """
        Processes key events from a specific evdev device.

        Args:
            device: The evdev input device to listen to.
        """
        try:
            async for event in device.async_read_loop():
                # Only handle keyboard events
                if event.type == evdev.ecodes.EV_KEY:
                    key_event = evdev.categorize(event)
                    scancode = key_event.scancode

                    # Update state
                    if key_event.keystate == evdev.KeyEvent.key_down:
                        self._keys_pressed.add(scancode)
                    elif key_event.keystate == evdev.KeyEvent.key_up:
                        self._keys_pressed.discard(scancode)

                    # Check for Ctrl + Space
                    is_ctrl = (
                        evdev.ecodes.KEY_LEFTCTRL in self._keys_pressed
                        or evdev.ecodes.KEY_RIGHTCTRL in self._keys_pressed
                    )
                    is_space = evdev.ecodes.KEY_SPACE in self._keys_pressed

                    should_suppress = False

                    if is_ctrl and is_space:
                        # Mark current keys (Ctrl and Space) for suppression
                        if evdev.ecodes.KEY_LEFTCTRL in self._keys_pressed:
                            self._suppressed_keys.add(evdev.ecodes.KEY_LEFTCTRL)
                        if evdev.ecodes.KEY_RIGHTCTRL in self._keys_pressed:
                            self._suppressed_keys.add(evdev.ecodes.KEY_RIGHTCTRL)
                        self._suppressed_keys.add(evdev.ecodes.KEY_SPACE)

                        if self.toggle:
                            # Toggle on key down (initial press)
                            if key_event.keystate == evdev.KeyEvent.key_down:
                                # Avoid repeat triggers if key is held
                                if scancode == evdev.ecodes.KEY_SPACE:
                                    self._toggle_state()
                        else:
                            self._start_recording()
                        should_suppress = True
                    else:
                        if not self.toggle and self.state == DaemonState.RECORDING:
                            self._stop_recording()

                    # If the key is in suppression list, we continue to suppress it
                    # until it is released.
                    if scancode in self._suppressed_keys:
                        should_suppress = True
                        if key_event.keystate == evdev.KeyEvent.key_up:
                            self._suppressed_keys.discard(scancode)

                    # Passthrough if not suppressed
                    if not should_suppress and self._uinput_device:
                        self._uinput_device.write_event(event)
                else:
                    # Non-keyboard events (e.g. sync events) are passed through
                    if self._uinput_device:
                        self._uinput_device.write_event(event)
        except (asyncio.CancelledError, asyncio.InvalidStateError):
            # This is expected during shutdown
            pass

    async def _main_loop(self) -> None:
        """
        The asynchronous main loop of the daemon.
        """
        # 1. Device discovery
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        keyboards = [d for d in devices if evdev.ecodes.EV_KEY in d.capabilities()]

        if self.device_path:
            keyboards = [
                k
                for k in keyboards
                if k.path == self.device_path or k.name == self.device_path
            ]

        if not keyboards:
            print(
                "No matching keyboard devices found. Check permissions or /dev/input/."
            )
            return

        # 2. Setup uinput
        # Merge all key capabilities from keyboards to create virtual device
        all_keys = set()
        for k in keyboards:
            all_keys.update(k.capabilities().get(evdev.ecodes.EV_KEY, []))

        try:
            self._uinput_device = evdev.UInput(
                {evdev.ecodes.EV_KEY: list(all_keys)},
                name="Harp Virtual Keyboard",
            )
        except (OSError, PermissionError):
            print(
                "Error creating uinput device. Run: sudo chmod 666 /dev/uinput or sudo modprobe uinput."
            )
            return

        # 3. Grab keyboards
        print(f"Listening on: {[k.name for k in keyboards]}")
        for k in keyboards:
            try:
                k.grab()
                self._grabbed_devices.append(k)
            except PermissionError:
                print(
                    f"Permission denied grabbing '{k.name}'. Run: sudo usermod -aG input $USER."
                )
                return

        # 4. Start event handling
        try:
            await asyncio.gather(*(self._handle_events(k) for k in keyboards))
        except (asyncio.CancelledError, asyncio.InvalidStateError):
            pass
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """
        Ensures all devices are ungrabbed and uinput is closed.
        """
        for k in self._grabbed_devices:
            try:
                k.ungrab()
            except Exception:
                pass
        self._grabbed_devices.clear()

        if self._uinput_device:
            try:
                self._uinput_device.close()
            except Exception:
                pass
            self._uinput_device = None

    def run(self) -> None:
        """
        Entry point to start the asynchronous event loop.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def exception_handler(loop, context):
            # Ignore InvalidStateError during shutdown, common with evdev
            exception = context.get("exception")
            if isinstance(exception, asyncio.InvalidStateError):
                return
            loop.default_exception_handler(context)

        loop.set_exception_handler(exception_handler)

        try:
            loop.run_until_complete(self._main_loop())
        except PermissionError:
            print(
                "Permission denied accessing /dev/input/. Run with sudo or add user to 'input' group."
            )
        except KeyboardInterrupt:
            print("\nDaemon stopped. Releasing devices...")
            # Cancel all running tasks
            for task in asyncio.all_tasks(loop):
                task.cancel()
            # Allow tasks to finish cancellation
            try:
                loop.run_until_complete(
                    asyncio.gather(*asyncio.all_tasks(loop), return_exceptions=True)
                )
            except Exception:
                pass
        finally:
            self._cleanup()
            loop.close()
