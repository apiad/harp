"""
Core logic for managing states and the background daemon loop.
"""

import asyncio
import subprocess
import time
from enum import Enum, auto
from typing import Optional

import evdev
import numpy as np
import sounddevice as sd
from pynput import keyboard
from rich.console import Console
from rich.status import Status
from rich.panel import Panel

from harp.audio import AudioStreamer
from harp.config import HarpConfig
from harp.input import IncrementalTyper, WaylandTyper
from harp.streaming import StreamingTranscriber
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
        self.config = config
        self.state: DaemonState = DaemonState.IDLE
        self._keys_pressed: set[int] = set()
        self._suppressed_keys: set[int] = set()
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

        # Streaming components (recreated each session).
        self._transcriber: Optional[StreamingTranscriber] = None
        self._inc_typer = IncrementalTyper(
            self.typer, is_paused=lambda: self.pause_typing
        )
        self._stream_task: Optional[asyncio.Task] = None
        self._last_consumed: int = 0

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
        if len(message) > 200:
            message = message[:197] + "..."
        try:
            subprocess.run(
                ["notify-send", "Harp", f"{title}: {message}", "-t", "3000"],
                check=False,
                capture_output=True,
            )
        except FileNotFoundError:
            pass

    def _play_chime(self, start: bool) -> None:
        try:
            sample_rate = 44100
            duration = 0.1
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
            freq = 880.0 if start else 440.0
            envelope = np.ones_like(t)
            ramp = int(0.01 * sample_rate)
            envelope[:ramp] = np.linspace(0, 1, ramp)
            envelope[-ramp:] = np.linspace(1, 0, ramp)
            wave = 0.5 * np.sin(2 * np.pi * freq * t) * envelope
            sd.play(wave, sample_rate)
        except Exception as e:
            self.console.print(f"[yellow]Failed to play chime: {e}[/]")

    def _release_modifiers(self) -> None:
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
        if self.state != DaemonState.IDLE:
            return
        self.state = DaemonState.RECORDING
        self._play_chime(start=True)
        self.audio_streamer.start_recording()
        self._transcriber = StreamingTranscriber(
            transcribe=self.whisper_engine.transcribe,
            window=self.config.stream_window,
            overlap=self.config.stream_overlap,
            language=self.config.local_language,
        )
        self._inc_typer = IncrementalTyper(
            self.typer, is_paused=lambda: self.pause_typing
        )
        self._last_consumed = 0
        try:
            self._stream_task = asyncio.create_task(self._stream_loop())
        except RuntimeError:
            # No running loop (e.g. invoked from sync context in tests).
            self._stream_task = None
        self.console.print("[bold green]capturing...[/]")
        self._notify("Status", "capturing")

    async def _stream_tick(self) -> None:
        if self._transcriber is None:
            return
        buf = self.audio_streamer.get_current_buffer().flatten()
        new = buf[self._last_consumed:]
        self._last_consumed = buf.shape[0]
        if new.size:
            self._transcriber.feed(new)
        try:
            loop = asyncio.get_running_loop()
            state = await loop.run_in_executor(None, self._transcriber.step)
        except Exception:
            return
        if self.config.type_result:
            self._inc_typer.update(state.full)

    async def _stream_loop(self) -> None:
        try:
            while self.state == DaemonState.RECORDING:
                await asyncio.sleep(self.config.stream_slide_interval)
                await self._stream_tick()
        except asyncio.CancelledError:
            pass

    async def _stop_recording(self) -> None:
        if self.state != DaemonState.RECORDING:
            return
        self.state = DaemonState.PROCESSING
        self._play_chime(start=False)
        if self._stream_task:
            self._stream_task.cancel()
            self._stream_task = None
        audio = self.audio_streamer.stop_recording().flatten()
        if self._transcriber is not None:
            extra = audio[self._last_consumed:]
            if extra.size:
                self._transcriber.feed(extra)
            try:
                loop = asyncio.get_running_loop()
                final = await loop.run_in_executor(
                    None, self._transcriber.finalize
                )
            except Exception as e:
                self.console.print(f"[bold red]Finalize failed: {e}[/]")
                final = None
            if final is not None:
                text = final.committed.strip()
                self.console.print(
                    Panel(
                        f"[italic green]{text}[/]",
                        title="[bold cyan]Result[/]",
                        border_style="cyan",
                    )
                )
                self._notify("Transcription Ready", text)
                if self.config.copy_result and text:
                    try:
                        import pyperclip

                        pyperclip.copy(text)
                    except Exception as e:
                        self.console.print(f"[yellow]Copy failed: {e}[/]")
                if self.config.type_result:
                    self._release_modifiers()
                    self._inc_typer.update(text)
        self.state = DaemonState.IDLE
        self._notify("Status", "idle")

    async def _toggle_state(self) -> None:
        if self.state == DaemonState.IDLE:
            self._start_recording()
        elif self.state == DaemonState.RECORDING:
            await self._stop_recording()

    async def _handle_events(self, device: evdev.InputDevice) -> None:
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
                    is_space = evdev.ecodes.KEY_SPACE in self._keys_pressed

                    should_suppress = False

                    if is_ctrl and is_space:
                        self._release_modifiers()

                        if evdev.ecodes.KEY_LEFTCTRL in self._keys_pressed:
                            self._suppressed_keys.add(evdev.ecodes.KEY_LEFTCTRL)
                        if evdev.ecodes.KEY_RIGHTCTRL in self._keys_pressed:
                            self._suppressed_keys.add(evdev.ecodes.KEY_RIGHTCTRL)
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
