from __future__ import annotations

import ctypes
import logging
import time

from voice_input.config import PasteSettings


class TextPaster:
    def __init__(self, settings: PasteSettings, logger: logging.Logger | None = None) -> None:
        self.settings = settings
        self.logger = logger or logging.getLogger(__name__)

    def paste(self, text: str) -> float:
        if self.settings.method != "clipboard_ctrl_v":
            raise ValueError(f"Unsupported paste method: {self.settings.method}")

        try:
            import pyperclip
        except ImportError as exc:
            raise RuntimeError("pyperclip is required for paste. Run .\\run.ps1 first.") from exc

        paste_text = text
        if self.settings.add_space_after_text and paste_text and not paste_text.endswith((" ", "\n", "\t")):
            paste_text += " "

        started = time.perf_counter()
        previous_clipboard = None
        had_clipboard = False

        if self.settings.restore_clipboard:
            try:
                previous_clipboard = pyperclip.paste()
                had_clipboard = True
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Could not read clipboard before paste: %s", exc)

        pyperclip.copy(paste_text)
        self._send_ctrl_v()
        time.sleep(max(0, self.settings.restore_delay_ms) / 1000.0)

        if self.settings.restore_clipboard and had_clipboard:
            try:
                pyperclip.copy(previous_clipboard)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Could not restore clipboard: %s", exc)

        return (time.perf_counter() - started) * 1000.0

    def _send_ctrl_v(self) -> None:
        try:
            self._send_ctrl_v_winapi()
            self.logger.info("Paste hotkey sent method=winapi")
            return
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("WinAPI paste failed, trying pynput: %s", exc)

        try:
            self._send_ctrl_v_pynput()
            self.logger.info("Paste hotkey sent method=pynput")
            return
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("pynput paste failed, trying pyautogui: %s", exc)

        try:
            import pyautogui

            pyautogui.PAUSE = 0.01
            pyautogui.hotkey("ctrl", "v")
            self.logger.info("Paste hotkey sent method=pyautogui")
        except ImportError as exc:
            raise RuntimeError("pyautogui is required as the final paste fallback. Run .\\run.ps1 first.") from exc

    @staticmethod
    def _send_ctrl_v_winapi() -> None:
        user32 = ctypes.windll.user32
        vk_ctrl = 0x11
        vk_v = 0x56
        key_up = 0x0002

        user32.keybd_event(vk_ctrl, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(vk_v, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(vk_v, 0, key_up, 0)
        time.sleep(0.02)
        user32.keybd_event(vk_ctrl, 0, key_up, 0)

    @staticmethod
    def _send_ctrl_v_pynput() -> None:
        from pynput.keyboard import Controller, Key

        keyboard = Controller()
        keyboard.press(Key.ctrl)
        time.sleep(0.02)
        keyboard.press("v")
        time.sleep(0.02)
        keyboard.release("v")
        time.sleep(0.02)
        keyboard.release(Key.ctrl)
