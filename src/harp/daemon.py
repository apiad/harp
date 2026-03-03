"""
Core logic for managing states and the background daemon loop.
"""

import asyncio
import subprocess
from enum import Enum, auto

import evdev

from harp.api import OpenRouterClient
from harp.audio import AudioStreamer
from harp.config import HarpoConfig
from harp.input import WaylandTyper


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
        self._is_command_mode: bool = False
        self._uinput_device: evdev.UInput | None = None
        self._grabbed_devices: list[evdev.InputDevice] = []
        self.audio_streamer = AudioStreamer()
        self.typer = WaylandTyper()

        # Load configuration and initialize API client
        self.config = HarpoConfig()
        self.api_client = OpenRouterClient(
            api_key=self.config.api_key,
            base_url=self.config.api_base_url,
        )

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
            mode_str = "command" if self._is_command_mode else "capturing"
            print(mode_str)
            self._notify("Status", mode_str)

    async def _stop_recording(self) -> None:
        """
        Transitions to PROCESSING, stops capture, and transcribes.
        """
        if self.state == DaemonState.RECORDING:
            self.state = DaemonState.PROCESSING
            audio_data = self.audio_streamer.stop_recording()
            print("idle")
            self._notify("Status", "idle")

            if audio_data.size > 0:
                try:
                    print("Transcribing...")
                    instruction = (
                        "Listen to the following audio and reply whatever it says."
                        if self._is_command_mode
                        else "Transcribe this audio exactly."
                    )
                    transcription = await self.api_client.transcribe(
                        audio_data=audio_data,
                        samplerate=self.audio_streamer.samplerate,
                        model=self.config.api_model,
                        instruction=instruction,
                    )

                    if transcription.startswith("Error:"):
                        raise Exception(transcription)

                    print(f"\nTranscription: {transcription}\n")

                    # Wait a bit for the user to release physical keys
                    await asyncio.sleep(0.2)

                    # Ensure all modifiers are logically UP before typing
                    if self._uinput_device:
                        for mod in [
                            evdev.ecodes.KEY_LEFTCTRL,
                            evdev.ecodes.KEY_RIGHTCTRL,
                            evdev.ecodes.KEY_LEFTSHIFT,
                            evdev.ecodes.KEY_RIGHTSHIFT,
                            evdev.ecodes.KEY_LEFTALT,
                            evdev.ecodes.KEY_RIGHTALT,
                            evdev.ecodes.KEY_LEFTMETA,
                            evdev.ecodes.KEY_RIGHTMETA,
                        ]:
                            self._uinput_device.write(evdev.ecodes.EV_KEY, mod, 0)
                        self._uinput_device.syn()

                    # Type the text into the active window
                    print("Typing...")
                    self.typer.type_text(transcription)

                except Exception as e:
                    error_msg = f"Transcription or typing failed: {e}"
                    print(error_msg)
                    self._notify("Error", error_msg)

            self.state = DaemonState.IDLE

    async def _toggle_state(self) -> None:
        """
        Toggles the daemon state between IDLE and RECORDING.
        """
        if self.state == DaemonState.IDLE:
            self._start_recording()
        elif self.state == DaemonState.RECORDING:
            await self._stop_recording()

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
                    is_shift = (
                        evdev.ecodes.KEY_LEFTSHIFT in self._keys_pressed
                        or evdev.ecodes.KEY_RIGHTSHIFT in self._keys_pressed
                    )
                    is_space = evdev.ecodes.KEY_SPACE in self._keys_pressed

                    should_suppress = False

                    if is_ctrl and is_space:
                        if self.state == DaemonState.IDLE:
                            # Update mode based on Shift key
                            self._is_command_mode = is_shift

                        if self._uinput_device:
                            # Emulate key up for ctrl and shift keys that leaked to the OS
                            if evdev.ecodes.KEY_LEFTCTRL in self._keys_pressed:
                                self._uinput_device.write(
                                    evdev.ecodes.EV_KEY, evdev.ecodes.KEY_LEFTCTRL, 0
                                )
                            if evdev.ecodes.KEY_RIGHTCTRL in self._keys_pressed:
                                self._uinput_device.write(
                                    evdev.ecodes.EV_KEY, evdev.ecodes.KEY_RIGHTCTRL, 0
                                )
                            if evdev.ecodes.KEY_LEFTSHIFT in self._keys_pressed:
                                self._uinput_device.write(
                                    evdev.ecodes.EV_KEY, evdev.ecodes.KEY_LEFTSHIFT, 0
                                )
                            if evdev.ecodes.KEY_RIGHTSHIFT in self._keys_pressed:
                                self._uinput_device.write(
                                    evdev.ecodes.EV_KEY, evdev.ecodes.KEY_RIGHTSHIFT, 0
                                )
                            self._uinput_device.syn()

                        # Mark current keys (Ctrl, Shift, Space) for suppression
                        if evdev.ecodes.KEY_LEFTCTRL in self._keys_pressed:
                            self._suppressed_keys.add(evdev.ecodes.KEY_LEFTCTRL)
                        if evdev.ecodes.KEY_RIGHTCTRL in self._keys_pressed:
                            self._suppressed_keys.add(evdev.ecodes.KEY_RIGHTCTRL)
                        if evdev.ecodes.KEY_LEFTSHIFT in self._keys_pressed:
                            self._suppressed_keys.add(evdev.ecodes.KEY_LEFTSHIFT)
                        if evdev.ecodes.KEY_RIGHTSHIFT in self._keys_pressed:
                            self._suppressed_keys.add(evdev.ecodes.KEY_RIGHTSHIFT)
                        self._suppressed_keys.add(evdev.ecodes.KEY_SPACE)

                        if self.toggle:
                            # Toggle on key down (initial press)
                            if key_event.keystate == evdev.KeyEvent.key_down:
                                # Avoid repeat triggers if key is held
                                if scancode == evdev.ecodes.KEY_SPACE:
                                    await self._toggle_state()
                        else:
                            self._start_recording()
                        should_suppress = True

                    else:
                        if not self.toggle and self.state == DaemonState.RECORDING:
                            await self._stop_recording()

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

        # Narrowly define a keyboard as having standard letter keys (A-Z)
        # And EXCLUDE our own virtual keyboard to avoid feedback loops
        def is_real_keyboard(d: evdev.InputDevice) -> bool:
            if d.name == "Harp Virtual Keyboard":
                return False

            capabilities = d.capabilities()
            if evdev.ecodes.EV_KEY not in capabilities:
                return False
            keys = capabilities[evdev.ecodes.EV_KEY]
            # Check if it has KEY_A through KEY_Z
            return all(
                k in keys for k in range(evdev.ecodes.KEY_A, evdev.ecodes.KEY_Z + 1)
            )

        keyboards = [d for d in devices if is_real_keyboard(d)]

        if self.device_path:
            keyboards = [
                k
                for k in keyboards
                if k.path == self.device_path or k.name == self.device_path
            ]

        if not keyboards:
            print("No real keyboard devices found. Check permissions or /dev/input/.")
            return

        # 2. Setup uinput
        # Merge all key capabilities from keyboards to create virtual device
        all_keys = set()
        for k in keyboards:
            all_keys.update(k.capabilities().get(evdev.ecodes.EV_KEY, []))

        try:
            self._uinput_device = evdev.UInput(
                {evdev.ecodes.EV_KEY: list(all_keys)},
                name="Harp Virtual passthrough",
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
