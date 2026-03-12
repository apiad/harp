"""
Core logic for managing states and the background daemon loop.
"""

import asyncio
import re
import subprocess
import time
from enum import Enum, auto
from typing import Optional

import evdev
import numpy as np
import pyperclip
import sounddevice as sd
from pynput import keyboard
from rich.console import Console
from rich.status import Status
from rich.panel import Panel

from harp.api import LLMClient
from harp.audio import AudioStreamer
from harp.config import HarpConfig
from harp.input import WaylandTyper
from harp.whisper import LocalWhisperEngine


class DaemonState(Enum):
    """
    Possible states for the Harp daemon.
    """

    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()


class HarpDaemon:
    """
    Manages the lifecycle of the Harp daemon.
    """

    def __init__(self, config: HarpConfig) -> None:
        """
        Initializes the HarpDaemon with its components and state.

        Args:
            config: The HarpConfig instance containing all settings.
        """
        self.config = config
        self.state: DaemonState = DaemonState.IDLE
        self._keys_pressed: set[int] = set()
        self._suppressed_keys: set[int] = set()
        self._is_command_mode: bool = False
        self._uinput_device: evdev.UInput | None = None
        self._grabbed_devices: list[evdev.InputDevice] = []
        self.audio_streamer = AudioStreamer()
        self.typer = WaylandTyper(full_mode=config.full_mode)

        # State for safety listener
        self._last_user_typing_time: float = 0.0
        self._keyboard_listener: keyboard.Listener | None = None

        # UI components
        self.console = Console()
        self._status: Status | None = None

        # Initialize Engines
        self.whisper_engine = LocalWhisperEngine(
            model_size=self.config.local_model,
            device=self.config.local_device,
            compute_type=self.config.local_compute_type,
        )

        self.llm_client = LLMClient(
            api_key=self.config.llm_api_key,
            base_url=self.config.llm_base_url,
        )

        # Background Transcription Task
        self._transcription_task: Optional[asyncio.Task] = None
        self._latest_transcription: str = ""

    @property
    def pause_typing(self) -> bool:
        """
        True if the user has typed recently (within 2 seconds).
        """
        return time.time() - self._last_user_typing_time < 2.0

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        """
        Callback for pynput keyboard listener.
        """
        self._last_user_typing_time = time.time()

    def _notify(self, title: str, message: str) -> None:
        """
        Sends a desktop notification using notify-send.

        Args:
            title: The title of the notification.
            message: The message body of the notification.
        """
        # Truncate message to avoid huge notifications
        if len(message) > 200:
            message = message[:197] + "..."
        try:
            subprocess.run(
                ["notify-send", "Harp", f"{title}: {message}", "-t", "3000"],
                check=False,
                capture_output=True,
            )
        except FileNotFoundError:
            # notify-send not available, ignore
            pass

    def _play_chime(self, start: bool) -> None:
        """
        Plays a small audio chime. High pitch for start, low pitch for stop.
        """
        try:
            sample_rate = 44100
            duration = 0.1
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)

            # Start: 880 Hz, Stop: 440 Hz
            freq = 880.0 if start else 440.0

            # Simple envelope to avoid clicking
            envelope = np.ones_like(t)
            ramp = int(0.01 * sample_rate)
            envelope[:ramp] = np.linspace(0, 1, ramp)
            envelope[-ramp:] = np.linspace(1, 0, ramp)

            wave = 0.5 * np.sin(2 * np.pi * freq * t) * envelope

            # Play non-blocking
            sd.play(wave, sample_rate)
        except Exception as e:
            self.console.print(f"[yellow]Failed to play chime: {e}[/]")

    def _get_clipboard_context(self, tokens_to_get: int) -> str | None:
        """
        Reads the clipboard and returns the last `tokens_to_get` words.
        Attempts to cut at a sentence boundary.
        """
        try:
            text = pyperclip.paste()
            if not text:
                return None

            # Split by whitespace, preserving it
            tokens = re.split(r"(\s+)", text)

            word_tokens = [t for t in tokens if t.strip()]
            if len(word_tokens) <= tokens_to_get:
                return text.strip()

            words_found = 0
            start_index = 0
            for i in range(len(tokens) - 1, -1, -1):
                if tokens[i].strip():
                    words_found += 1
                if words_found == tokens_to_get:
                    start_index = i
                    break

            truncated = "".join(tokens[start_index:]).lstrip()

            # Look for sentence boundary: punctuation followed by space and uppercase
            match = re.search(r"[.!?]\s+([A-Z])", truncated)
            if match:
                # Cut at the start of the uppercase letter
                return truncated[match.start(1) :]
            else:
                return f"[...] {truncated}"

        except Exception as e:
            self.console.print(f"[yellow]Failed to read clipboard: {e}[/]")
            return None

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

    async def _background_transcription_loop(self) -> None:
        """
        Periodically transcribes new audio chunks when continuous mode is enabled.
        """
        if not self.config.continuous:
            return

        sample_rate = 16000
        transcribed_seconds = 0.0

        while self.state == DaemonState.RECORDING:
            await asyncio.sleep(0.5)

            # Get full audio data
            audio_data = self.audio_streamer.get_current_buffer()
            current_duration = audio_data.size / sample_rate

            # Should we transcribe?
            should_transcribe = False
            if transcribed_seconds == 0:
                # First pass after min_chunk_size
                if current_duration >= self.config.stt_min_chunk_size:
                    should_transcribe = True
            else:
                # Subsequent passes after slide_interval
                if (
                    current_duration - transcribed_seconds
                    >= self.config.stt_slide_interval
                ):
                    should_transcribe = True

            if not should_transcribe:
                continue

            # Calculate chunk to transcribe (with overlap)
            start_sec = max(0, transcribed_seconds - self.config.stt_overlap)
            start_idx = int(start_sec * sample_rate)
            chunk = audio_data.flatten()[start_idx:]

            if chunk.size == 0:
                continue

            try:
                loop = asyncio.get_event_loop()
                # Use latest transcription as prompt for consistency
                # Limit prompt size to avoid token bloat
                prompt = (
                    self._latest_transcription[-200:]
                    if self._latest_transcription
                    else None
                )

                new_text = await loop.run_in_executor(
                    None,
                    self.whisper_engine.transcribe,
                    chunk,
                    prompt,
                    self.config.local_language,
                )

                if new_text:
                    # Simple stitching: for background feedback, we just update the latest
                    # because we will do a full high-accuracy pass at the end anyway.
                    # We print it dimmed to the console.
                    self._latest_transcription = new_text
                    self.console.print(f"[dim]... {new_text}[/dim]")

                transcribed_seconds = current_duration

            except Exception:
                # Silently ignore background errors
                pass

    def _start_recording(self) -> None:
        """
        Transitions to RECORDING and starts audio capture.
        """
        if self.state == DaemonState.IDLE:
            self._latest_transcription = ""
            self.state = DaemonState.RECORDING
            self._play_chime(start=True)
            self.audio_streamer.start_recording()

            # Start background transcription
            self._transcription_task = asyncio.create_task(
                self._background_transcription_loop()
            )

            mode_str = "command" if self._is_command_mode else "capturing"
            self.console.print(f"[bold green]{mode_str}...[/]")
            self._notify("Status", mode_str)

    async def _stop_recording(self) -> None:
        """
        Transitions to PROCESSING, stops capture, and transcribes.
        """
        if self.state == DaemonState.RECORDING:
            self.state = DaemonState.PROCESSING
            self._play_chime(start=False)

            # Cancel background task and get final audio
            if self._transcription_task:
                self._transcription_task.cancel()

            audio_data = self.audio_streamer.stop_recording()
            self.console.print("[bold blue]idle[/]")
            self._notify("Status", "idle")

            if audio_data.size > 0:
                with self.console.status(
                    "[bold blue]Finalizing transcription...[/]"
                ) as status:
                    try:
                        # Perform final transcription of the full buffer
                        # We use run_in_executor to keep UI responsive
                        loop = asyncio.get_running_loop()
                        transcription = await loop.run_in_executor(
                            None,
                            self.whisper_engine.transcribe,
                            audio_data.flatten(),
                            None,
                            self.config.local_language,
                        )

                        if not transcription:
                            transcription = self._latest_transcription

                        if self._is_command_mode:
                            instruction = self.config.command_prompt

                            if self.config.send_clipboard > 0:
                                context = self._get_clipboard_context(
                                    self.config.send_clipboard
                                )
                                if context:
                                    instruction += f"\n\nHere is context from clipboard:\n<context>\n{context}\n</context>"

                            self.console.print(
                                Panel(
                                    f"[dim]{instruction}[/dim]",
                                    title="[cyan]Instruction[/]",
                                    border_style="cyan",
                                )
                            )

                            status.update(
                                "[bold blue]Processing command with LLM...[/]"
                            )
                            transcription = await self.llm_client.process_text(
                                text=transcription,
                                instruction=instruction,
                                model=self.config.llm_model,
                            )

                        # ALWAYS print to CLI
                        self.console.print(
                            Panel(
                                f"[italic green]{transcription}[/]",
                                title="[bold cyan]Result[/]",
                                border_style="cyan",
                            )
                        )
                        self._notify("Transcription Ready", transcription)

                        if self.config.copy_result:
                            try:
                                pyperclip.copy(transcription)
                                self.console.print(
                                    "[bold green]Copied to clipboard![/]"
                                )
                            except Exception as e:
                                self.console.print(f"[yellow]Failed to copy: {e}[/]")

                        await asyncio.sleep(0.5)
                        self._release_modifiers()

                        if self.config.type_result:
                            filtered_final = self.typer.filter_text(transcription)
                            if filtered_final:
                                status.update("[bold cyan]Typing result...[/]")
                                self.typer.type_text(filtered_final)

                    except Exception as e:
                        error_msg = f"Transcription or typing failed: {e}"
                        self.console.print(f"[bold red]{error_msg}[/]")
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
                if event.type == evdev.ecodes.EV_KEY:
                    key_event = evdev.categorize(event)
                    scancode = key_event.scancode

                    if key_event.keystate == evdev.KeyEvent.key_down:
                        self._keys_pressed.add(scancode)
                    elif key_event.keystate == evdev.KeyEvent.key_up:
                        self._keys_pressed.discard(scancode)

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
                            self._is_command_mode = is_shift

                        self._release_modifiers()

                        if evdev.ecodes.KEY_LEFTCTRL in self._keys_pressed:
                            self._suppressed_keys.add(evdev.ecodes.KEY_LEFTCTRL)
                        if evdev.ecodes.KEY_RIGHTCTRL in self._keys_pressed:
                            self._suppressed_keys.add(evdev.ecodes.KEY_RIGHTCTRL)
                        if evdev.ecodes.KEY_LEFTSHIFT in self._keys_pressed:
                            self._suppressed_keys.add(evdev.ecodes.KEY_LEFTSHIFT)
                        if evdev.ecodes.KEY_RIGHTSHIFT in self._keys_pressed:
                            self._suppressed_keys.add(evdev.ecodes.KEY_RIGHTSHIFT)
                        self._suppressed_keys.add(evdev.ecodes.KEY_SPACE)

                        if self.config.toggle:
                            if key_event.keystate == evdev.KeyEvent.key_down:
                                if scancode == evdev.ecodes.KEY_SPACE:
                                    await self._toggle_state()
                        else:
                            self._start_recording()
                        should_suppress = True

                    else:
                        if (
                            not self.config.toggle
                            and self.state == DaemonState.RECORDING
                        ):
                            await self._stop_recording()

                    if scancode in self._suppressed_keys:
                        should_suppress = True
                        if key_event.keystate == evdev.KeyEvent.key_up:
                            self._suppressed_keys.discard(scancode)

                    if not should_suppress and self._uinput_device:
                        self._uinput_device.write_event(event)
                else:
                    if self._uinput_device:
                        self._uinput_device.write_event(event)
        except (asyncio.CancelledError, asyncio.InvalidStateError):
            pass

    @staticmethod
    def _is_real_keyboard(device: evdev.InputDevice) -> bool:
        """
        Narrowly defines a keyboard as having standard letter keys (A-Z)
        and excluding our own virtual devices.
        """
        if "Harp Virtual" in device.name:
            return False

        if "keyboard" not in device.name.lower():
            return False

        capabilities = device.capabilities()
        if evdev.ecodes.EV_KEY not in capabilities:
            return False
        keys = capabilities[evdev.ecodes.EV_KEY]
        return all(k in keys for k in range(evdev.ecodes.KEY_A, evdev.ecodes.KEY_Z + 1))

    async def _main_loop(self) -> None:
        """
        The asynchronous main loop of the daemon.
        """
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        keyboards = [d for d in devices if self._is_real_keyboard(d)]

        if self.config.device:
            keyboards = [
                k
                for k in keyboards
                if k.path == self.config.device or k.name == self.config.device
            ]

        if not keyboards:
            self.console.print("[bold red]No keyboard found.[/]")
            return

        all_keys = set()
        for k in keyboards:
            all_keys.update(k.capabilities().get(evdev.ecodes.EV_KEY, []))

        try:
            self._uinput_device = evdev.UInput(
                {evdev.ecodes.EV_KEY: list(all_keys)},
                name="Harp Virtual passthrough",
            )
        except (OSError, PermissionError):
            self.console.print("[bold red]Error creating uinput device.[/]")
            return

        self.console.print(f"[bold cyan]Listening on:[/] {[k.name for k in keyboards]}")
        for k in keyboards:
            try:
                k.grab()
                self._grabbed_devices.append(k)
            except PermissionError:
                self.console.print(
                    f"[bold red]Permission denied grabbing '{k.name}'.[/]"
                )
                return

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
        if self._keyboard_listener:
            try:
                self._keyboard_listener.stop()
            except Exception:
                pass
            self._keyboard_listener = None

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
        self._keyboard_listener = keyboard.Listener(on_press=self._on_press)
        self._keyboard_listener.start()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def exception_handler(loop, context):
            exception = context.get("exception")
            if isinstance(exception, asyncio.InvalidStateError):
                return
            loop.default_exception_handler(context)

        loop.set_exception_handler(exception_handler)

        try:
            loop.run_until_complete(self._main_loop())
        except PermissionError:
            self.console.print("[bold red]Permission denied accessing /dev/input/.[/]")
        except KeyboardInterrupt:
            self.console.print("\n[bold yellow]Daemon stopped.[/]")
            for task in asyncio.all_tasks(loop):
                task.cancel()
            try:
                loop.run_until_complete(
                    asyncio.gather(*asyncio.all_tasks(loop), return_exceptions=True)
                )
            except Exception:
                pass
        finally:
            self._cleanup()
            loop.close()
