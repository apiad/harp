"""evdev hotkey watcher + pure state machine for Ctrl+Space."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, List, Optional

import evdev


KEY_LEFTCTRL = 29
KEY_RIGHTCTRL = 97
KEY_SPACE = 57


@dataclass(frozen=True)
class KeyEvent:
    code: int
    down: bool  # True = key_down, False = key_up


class HotkeyAction(Enum):
    START = auto()
    STOP = auto()


class HotkeyStateMachine:
    """Pure state machine — no evdev, no threads, no I/O. Drive with KeyEvents.

    Returns ``HotkeyAction`` when Ctrl+Space transitions cross a session
    boundary, or ``None`` otherwise.
    """

    def __init__(self, toggle: bool = False) -> None:
        self._toggle = toggle
        self._pressed: set[int] = set()
        self._recording = False

    def _ctrl_down(self) -> bool:
        return KEY_LEFTCTRL in self._pressed or KEY_RIGHTCTRL in self._pressed

    def handle(self, ev: KeyEvent) -> Optional[HotkeyAction]:
        if ev.down:
            self._pressed.add(ev.code)
        else:
            self._pressed.discard(ev.code)

        ctrl_space_now = self._ctrl_down() and KEY_SPACE in self._pressed

        if self._toggle:
            # Toggle: only react on Ctrl+Space key_down transitions to KEY_SPACE.
            if ev.down and ev.code == KEY_SPACE and self._ctrl_down():
                if not self._recording:
                    self._recording = True
                    return HotkeyAction.START
                else:
                    self._recording = False
                    return HotkeyAction.STOP
            return None

        # Hold mode.
        if ctrl_space_now and not self._recording:
            self._recording = True
            return HotkeyAction.START
        if self._recording and not ctrl_space_now:
            self._recording = False
            return HotkeyAction.STOP
        return None


# --- evdev I/O wrapper (no unit tests; covered by manual smoke) ---


class HotkeyWatcher:
    """Owns the evdev grab loop. Calls ``on_start`` / ``on_stop`` when the
    state machine signals a session boundary. Runs in its own asyncio loop
    on a worker thread so the main thread can drive Rich Live.
    """

    def __init__(
        self,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        toggle: bool = False,
        device_filter: Optional[str] = None,
    ) -> None:
        self._on_start = on_start
        self._on_stop = on_stop
        self._sm = HotkeyStateMachine(toggle=toggle)
        self._device_filter = device_filter
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._uinput_device: Optional[evdev.UInput] = None
        self._grabbed: List[evdev.InputDevice] = []
        self._suppress: set[int] = set()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._cleanup()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        finally:
            self._cleanup()

    async def _main(self) -> None:
        keyboards = self._open_keyboards()
        if not keyboards:
            return
        await asyncio.gather(*(self._handle(k) for k in keyboards))

    def _open_keyboards(self) -> List[evdev.InputDevice]:
        devices = [evdev.InputDevice(p) for p in evdev.list_devices()]
        keyboards = [d for d in devices if self._is_real_keyboard(d)]
        if self._device_filter:
            keyboards = [
                k for k in keyboards
                if k.path == self._device_filter or k.name == self._device_filter
            ]
        if not keyboards:
            return []
        all_keys: set = set()
        for k in keyboards:
            all_keys.update(k.capabilities().get(evdev.ecodes.EV_KEY, []))
        try:
            self._uinput_device = evdev.UInput(
                {evdev.ecodes.EV_KEY: list(all_keys)},
                name="Harp Virtual passthrough",
            )
        except (OSError, PermissionError):
            return []
        for k in keyboards:
            try:
                k.grab()
                self._grabbed.append(k)
            except PermissionError:
                return []
        return keyboards

    @staticmethod
    def _is_real_keyboard(device: evdev.InputDevice) -> bool:
        if "Harp Virtual" in device.name:
            return False
        if "keyboard" not in device.name.lower():
            return False
        caps = device.capabilities()
        if evdev.ecodes.EV_KEY not in caps:
            return False
        keys = caps[evdev.ecodes.EV_KEY]
        return all(k in keys for k in range(evdev.ecodes.KEY_A, evdev.ecodes.KEY_Z + 1))

    async def _handle(self, device: evdev.InputDevice) -> None:
        async for event in device.async_read_loop():
            if event.type != evdev.ecodes.EV_KEY:
                if self._uinput_device:
                    self._uinput_device.write_event(event)
                continue
            ke = evdev.categorize(event)
            if ke.keystate == evdev.KeyEvent.key_down:
                action = self._sm.handle(KeyEvent(code=ke.scancode, down=True))
                self._suppress_if_hotkey(ke.scancode, True)
            elif ke.keystate == evdev.KeyEvent.key_up:
                action = self._sm.handle(KeyEvent(code=ke.scancode, down=False))
                self._suppress_if_hotkey(ke.scancode, False)
            else:
                action = None

            if action == HotkeyAction.START:
                self._on_start()
            elif action == HotkeyAction.STOP:
                self._on_stop()

            if ke.scancode not in self._suppress and self._uinput_device:
                self._uinput_device.write_event(event)

    def _suppress_if_hotkey(self, code: int, down: bool) -> None:
        if code in (KEY_LEFTCTRL, KEY_RIGHTCTRL, KEY_SPACE):
            if down:
                self._suppress.add(code)
            else:
                self._suppress.discard(code)

    def _cleanup(self) -> None:
        for k in self._grabbed:
            try:
                k.ungrab()
            except Exception:
                pass
        self._grabbed.clear()
        if self._uinput_device:
            try:
                self._uinput_device.close()
            except Exception:
                pass
            self._uinput_device = None
