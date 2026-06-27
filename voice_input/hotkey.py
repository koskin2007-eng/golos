from __future__ import annotations

import logging
from collections.abc import Callable


ALIASES = {
    "control": "ctrl",
    "ctl": "ctrl",
    "escape": "esc",
    "return": "enter",
    "windows": "win",
    "cmd": "win",
    "command": "win",
}


def parse_hotkey(hotkey: str) -> set[str]:
    tokens = [part.strip().lower() for part in hotkey.replace("-", "+").split("+")]
    normalized = {ALIASES.get(token, token) for token in tokens if token}
    if not normalized:
        raise ValueError("Hotkey must not be empty.")
    return normalized


class PushToTalkHotkey:
    def __init__(
        self,
        hotkey: str,
        on_pressed: Callable[[], None],
        on_released: Callable[[], None],
        logger: logging.Logger | None = None,
    ) -> None:
        self.hotkey = hotkey
        self.tokens = parse_hotkey(hotkey)
        self.on_pressed = on_pressed
        self.on_released = on_released
        self.logger = logger or logging.getLogger(__name__)
        self._pressed: set[str] = set()
        self._active = False
        self._listener = None
        self._keyboard = None

    def start(self) -> None:
        try:
            from pynput import keyboard
        except ImportError as exc:
            raise RuntimeError("pynput is required for global hotkeys. Run .\\run.ps1 first.") from exc

        self._keyboard = keyboard
        self._listener = keyboard.Listener(on_press=self._handle_press, on_release=self._handle_release)
        self._listener.start()
        self.logger.info("Global push-to-talk hotkey registered hotkey=%s", self.hotkey)

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _handle_press(self, key) -> None:  # noqa: ANN001
        name = self._normalize_key(key)
        if not name:
            return
        self._pressed.add(name)
        if not self._active and self.tokens.issubset(self._pressed):
            self._active = True
            try:
                self.on_pressed()
            except Exception:  # noqa: BLE001
                self.logger.exception("Hotkey press handler failed")

    def _handle_release(self, key) -> None:  # noqa: ANN001
        name = self._normalize_key(key)
        if not name:
            return

        should_release = self._active and name in self.tokens
        self._pressed.discard(name)

        if should_release:
            self._active = False
            try:
                self.on_released()
            except Exception:  # noqa: BLE001
                self.logger.exception("Hotkey release handler failed")

    def _normalize_key(self, key) -> str | None:  # noqa: ANN001
        keyboard = self._keyboard
        if keyboard is None:
            return None

        if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            return "ctrl"
        if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            return "shift"
        if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
            return "alt"
        if key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
            return "win"

        char = getattr(key, "char", None)
        if char:
            return char.lower()

        name = getattr(key, "name", None)
        if name:
            return ALIASES.get(name.lower(), name.lower())
        return None

