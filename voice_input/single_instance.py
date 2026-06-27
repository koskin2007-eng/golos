from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


ERROR_ALREADY_EXISTS = 183
DEFAULT_MUTEX_NAME = "Local\\VoiceInputPushToTalk"


class SingleInstanceGuard:
    def __init__(self, name: str = DEFAULT_MUTEX_NAME) -> None:
        self.name = name
        self._kernel32 = None
        self._handle: int | None = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True

        if os.name != "nt":
            return True

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())

        self._kernel32 = kernel32
        self._handle = handle

        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            self.release()
            return False

        return True

    def release(self) -> None:
        if self._handle is None or self._kernel32 is None:
            self._handle = None
            return

        self._kernel32.CloseHandle(self._handle)
        self._handle = None
