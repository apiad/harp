"""
Core logic for managing states and the background daemon loop.
"""

import asyncio
import subprocess
from enum import Enum, auto

import evdev
from rich.console import Console
from rich.status import Status
from rich.panel import Panel

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

    def __init__(
        self,
        device_path: str | None = None,
        toggle: bool = False,
        full_mode: bool = False,
        interactive: bool = False,
        interval: float = 2.0,
    ) -> None:
        """
        Initializes the HarpoDaemon with its components and state.

        Args:
            device_path: Optional path or name of the device to grab.
            toggle: Whether to toggle state on keypress.
            full_mode: Whether to type all characters or just a safe set.
            interactive: Whether to enable real-time transcription.
            interval: Sampling interval for interactive mode.
        """
        self.device_path: str | None = device_path
        self.toggle: bool = toggle
        self.full_mode: bool = full_mode
        self.interactive: bool = interactive
        self.interval: float = interval

        self.state: DaemonState = DaemonState.IDLE
        self._keys_pressed: set[int] = set()
        self._suppressed_keys: set[int] = set()
        self._is_command_mode: bool = False
        self._uinput_device: evdev.UInput | None = None
        self._grabbed_devices: list[evdev.InputDevice] = []
        self.audio_streamer = AudioStreamer()
        self.typer = WaylandTyper(full_mode=full_mode)

        # State for interactive mode
        self.current_session_text: str = ""
        self._interactive_task: asyncio.Task | None = None
        self._interactive_lock = asyncio.Lock()

        # UI components
        self.console = Console()
        self._status: Status | None = None

        # Load configuration and initialize API client
        self.config = HarpoConfig()
        self.api_client = OpenRouterClient(
            api_key=self.config.api_key,
            base_url=self.config.api_base_url,
        )

        if self.interactive:
            self.console.print(
                Panel(
                    "[bold red]INTERACTIVE MODE IS EXPERIMENTAL AND CURRENTLY BROKEN[/]\n"
                    "[red]It may produce weird typing behavior or out-of-sync text.[/]",
                    title="[bold yellow]WARNING[/]",
                    border_style="red",
                )
            )

    def _notify(self, title: str, message: str) -> None:
        """
        Sends a desktop notification using notify-send.

        Args:
            title: The title of the notification.
            message: The message body of the notification.
        """
        subprocess.run(["notify-send", "Harp", f"{title}: {message}", "-t", "1000"])

    def _release_modifiers(self) -> None:
        """
        Ensures all modifier keys are logically UP on the virtual passthrough device.
        """
        if not self._uinput_device:
            return

        modifiers = [
            evdev.ecodes.KEY_LEFTCTRL,
            evdev.ecodes.KEY_RIGHTCTRL,
            evdev.ecodes.KEY_LEFTSHIFT,
            evdev.ecodes.KEY_RIGHTSHIFT,
            evdev.ecodes.KEY_LEFTALT,
            evdev.ecodes.KEY_RIGHTALT,
            evdev.ecodes.KEY_LEFTMETA,
            evdev.ecodes.KEY_RIGHTMETA,
        ]

        for mod in modifiers:
            self._uinput_device.write(evdev.ecodes.EV_KEY, mod, 0)
        self._uinput_device.syn()

    def _start_recording(self) -> None:
        """
        Transitions to RECORDING and starts audio capture.
        """
        if self.state == DaemonState.IDLE:
            self.state = DaemonState.RECORDING
            self.current_session_text = ""
            self.audio_streamer.start_recording()
            mode_str = "command" if self._is_command_mode else "capturing"
            self.console.print(f"[bold green]{mode_str}...[/]")
            self._notify("Status", mode_str)

            if self.interactive:
                self._interactive_task = asyncio.create_task(self._interactive_loop())

    async def _interactive_loop(self) -> None:
        """
        Periodically samples audio and types incremental transcription.
        """
        try:
            while self.state == DaemonState.RECORDING:
                # Wait FIRST to allow some audio to accumulate
                await asyncio.sleep(self.interval)

                async with self._interactive_lock:
                    if self.state != DaemonState.RECORDING:
                        break

                    audio_data = self.audio_streamer.get_current_buffer()
                    if audio_data.size == 0:
                        continue

                    instruction = (
                        "Listen to the following audio and reply whatever it says."
                        if self._is_command_mode
                        else "Transcribe this audio exactly."
                    )

                    # Fetch transcription
                    raw_text = await self.api_client.transcribe(
                        audio_data=audio_data,
                        samplerate=self.audio_streamer.samplerate,
                        model=self.config.api_model,
                        instruction=instruction,
                    )

                    if (
                        raw_text.startswith("Error:")
                        or self.state != DaemonState.RECORDING
                    ):
                        continue

                    new_text = self.typer.filter_text(raw_text)

                    if new_text == self.current_session_text:
                        pass
                    elif new_text.startswith(self.current_session_text):
                        # Type only the suffix
                        suffix = new_text[len(self.current_session_text) :]
                        if suffix:
                            self._release_modifiers()
                            self.typer.type_text(suffix)
                            self.current_session_text = new_text
                    else:
                        # Whisper refined the beginning, replace everything
                        self._release_modifiers()
                        self.typer.backspace(len(self.current_session_text))
                        self.typer.type_text(new_text)
                        self.current_session_text = new_text

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.console.print(f"[bold red]Error in interactive loop: {e}[/]")

    async def _stop_recording(self) -> None:
        """
        Transitions to PROCESSING, stops capture, and transcribes.
        """
        if self.state == DaemonState.RECORDING:
            self.state = DaemonState.PROCESSING

            # Cancel interactive task
            if self._interactive_task:
                self._interactive_task.cancel()
                try:
                    await self._interactive_task
                except asyncio.exceptions.CancelledError:
                    pass
                self._interactive_task = None

            audio_data = self.audio_streamer.stop_recording()
            self.console.print("[bold blue]idle[/]")
            self._notify("Status", "idle")

            if audio_data.size > 0:
                with self.console.status("[bold blue]Transcribing...[/]") as status:
                    try:
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

                        self.console.print(
                            Panel(
                                f"[italic green]{transcription}[/]",
                                title="[bold cyan]Transcription[/]",
                                border_style="cyan",
                            )
                        )

                        # Wait a bit for the user to release physical keys
                        await asyncio.sleep(0.5)
                        self._release_modifiers()

                        # Final reconciliation with interactive text
                        filtered_final = self.typer.filter_text(transcription)

                        if filtered_final == self.current_session_text:
                            # Nothing more to type
                            pass
                        elif filtered_final.startswith(self.current_session_text):
                            # Just type the missing suffix
                            suffix = filtered_final[len(self.current_session_text) :]
                            if suffix:
                                status.update("[bold cyan]Typing final suffix...[/]")
                                self.typer.type_text(suffix)
                        else:
                            # Full replacement to ensure correctness
                            status.update("[bold cyan]Updating transcription...[/]")
                            if self.current_session_text:
                                self.typer.backspace(len(self.current_session_text))
                            self.typer.type_text(filtered_final)

                    except Exception as e:
                        error_msg = f"Transcription or typing failed: {e}"
                        self.console.print(f"[bold red]{error_msg}[/]")
                        self._notify("Error", error_msg)

            self.current_session_text = ""
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

                        self._release_modifiers()

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
            if "Harp Virtual" in d.name:
                return False

            # Require "keyboard" in the name (case-insensitive)
            if "keyboard" not in d.name.lower():
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
            self.console.print(
                "[bold red]No real keyboard devices found. Check permissions or /dev/input/.[/]"
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
                name="Harp Virtual passthrough",
            )
        except (OSError, PermissionError):
            self.console.print(
                "[bold red]Error creating uinput device.[/] Run: [italic]sudo chmod 666 /dev/uinput[/] or [italic]sudo modprobe uinput[/]."
            )
            return

        # 3. Grab keyboards
        self.console.print(f"[bold cyan]Listening on:[/] {[k.name for k in keyboards]}")
        for k in keyboards:
            try:
                k.grab()
                self._grabbed_devices.append(k)
            except PermissionError:
                self.console.print(
                    f"[bold red]Permission denied grabbing '{k.name}'.[/] Run: [italic]sudo usermod -aG input $USER[/]."
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
            self.console.print(
                "[bold red]Permission denied accessing /dev/input/.[/] Run with sudo or add user to 'input' group."
            )
        except KeyboardInterrupt:
            self.console.print("\n[bold yellow]Daemon stopped. Releasing devices...[/]")
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
