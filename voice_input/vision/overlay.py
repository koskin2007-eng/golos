from __future__ import annotations

import ctypes
import logging
import tkinter as tk
from collections.abc import Callable

from PIL import Image, ImageGrab


SelectionCallback = Callable[[Image.Image], None]
CancelCallback = Callable[[], None]


def select_screen_region(
    on_selected: SelectionCallback,
    on_cancelled: CancelCallback,
    logger: logging.Logger | None = None,
) -> None:
    log = logger or logging.getLogger(__name__)
    _enable_dpi_awareness(log)
    screenshot = ImageGrab.grab(all_screens=True)
    left, top, width, height = _virtual_screen_geometry(screenshot)

    root = tk.Tk()
    root.withdraw()
    state: dict[str, object] = {
        "start": None,
        "anchor_monitor": None,
        "rectangles": [],
        "finished": False,
    }
    windows: list[tuple[tk.Toplevel, tuple[int, int, int, int]]] = []
    surfaces: list[tuple[tk.Canvas, tuple[int, int, int, int]]] = []

    def cancel(_event=None) -> None:  # noqa: ANN001
        if state["finished"]:
            return
        state["finished"] = True
        root.destroy()
        on_cancelled()

    def press(event: tk.Event, canvas: tk.Canvas, monitor: tuple[int, int, int, int]) -> None:
        for previous_canvas, rectangle in state.get("rectangles", []):
            previous_canvas.delete(rectangle)
        monitor_left, monitor_top, _monitor_width, _monitor_height = monitor
        state["start"] = (monitor_left + event.x, monitor_top + event.y)
        state["anchor_monitor"] = monitor
        state["rectangles"] = []
        draw_selection(monitor_left + event.x, monitor_top + event.y)

    def draw_selection(current_x: int, current_y: int) -> None:
        start = state.get("start")
        if start is None:
            return
        for previous_canvas, rectangle in state.get("rectangles", []):
            previous_canvas.delete(rectangle)
        start_x, start_y = start
        global_x1, global_x2 = sorted((start_x, current_x))
        global_y1, global_y2 = sorted((start_y, current_y))
        rectangles: list[tuple[tk.Canvas, int]] = []
        for surface, (monitor_left, monitor_top, monitor_width, monitor_height) in surfaces:
            x1 = max(global_x1, monitor_left)
            y1 = max(global_y1, monitor_top)
            x2 = min(global_x2, monitor_left + monitor_width)
            y2 = min(global_y2, monitor_top + monitor_height)
            if x2 < x1 or y2 < y1:
                continue
            rectangle = surface.create_rectangle(
                x1 - monitor_left,
                y1 - monitor_top,
                x2 - monitor_left,
                y2 - monitor_top,
                outline="#facc15",
                width=3,
                fill="",
            )
            rectangles.append((surface, rectangle))
        state["rectangles"] = rectangles

    def drag(event: tk.Event) -> None:
        monitor = state.get("anchor_monitor")
        if monitor is None:
            return
        monitor_left, monitor_top, _monitor_width, _monitor_height = monitor
        draw_selection(monitor_left + event.x, monitor_top + event.y)

    def release(event: tk.Event) -> None:
        start = state.get("start")
        monitor = state.get("anchor_monitor")
        if start is None or monitor is None or state["finished"]:
            return
        monitor_left, monitor_top, _monitor_width, _monitor_height = monitor
        start_x, start_y = start
        current_x = monitor_left + event.x
        current_y = monitor_top + event.y
        x1, x2 = sorted((max(left, min(left + width, start_x)), max(left, min(left + width, current_x))))
        y1, y2 = sorted((max(top, min(top + height, start_y)), max(top, min(top + height, current_y))))
        if x2 - x1 < 12 or y2 - y1 < 12:
            return
        state["finished"] = True
        crop = screenshot.crop((x1 - left, y1 - top, x2 - left, y2 - top)).copy()
        root.destroy()
        on_selected(crop)

    for monitor in _monitor_geometries((left, top, width, height)):
        monitor_left, monitor_top, monitor_width, monitor_height = monitor
        window = tk.Toplevel(root)
        window.title("Голос — перевод экрана")
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.geometry(f"{monitor_width}x{monitor_height}{monitor_left:+d}{monitor_top:+d}")
        window.configure(cursor="crosshair")
        window.attributes("-alpha", 0.28)
        canvas = tk.Canvas(
            window,
            width=monitor_width,
            height=monitor_height,
            background="black",
            highlightthickness=0,
            cursor="crosshair",
        )
        canvas.pack(fill="both", expand=True)
        canvas.create_text(
            monitor_width // 2,
            34,
            text="Выделите текст для перевода • Esc — отмена",
            fill="white",
            font=("Segoe UI", 13, "bold"),
        )
        window.bind("<Escape>", cancel)
        canvas.bind("<ButtonPress-1>", lambda event, c=canvas, m=monitor: press(event, c, m))
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", release)
        windows.append((window, monitor))
        surfaces.append((canvas, monitor))

    root.update_idletasks()
    for window, monitor in windows:
        _place_window_in_physical_pixels(window, monitor, log)
    pointer_x, pointer_y = root.winfo_pointerx(), root.winfo_pointery()
    focus_window = next(
        (
            window
            for window, (monitor_left, monitor_top, monitor_width, monitor_height) in windows
            if monitor_left <= pointer_x < monitor_left + monitor_width
            and monitor_top <= pointer_y < monitor_top + monitor_height
        ),
        windows[0][0],
    )
    focus_window.focus_force()
    root.mainloop()


def _place_window_in_physical_pixels(
    window: tk.Toplevel,
    monitor: tuple[int, int, int, int],
    logger: logging.Logger,
) -> None:
    if not hasattr(ctypes, "windll"):
        return
    left, top, width, height = monitor
    user32 = ctypes.windll.user32
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetParent.restype = ctypes.c_void_p
    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetWindowRect.restype = ctypes.c_int
    tkinter_handle = int(window.winfo_id())
    native_handle = int(user32.GetParent(tkinter_handle)) or tkinter_handle
    hwnd_topmost = -1
    swp_showwindow = 0x0040
    if not user32.SetWindowPos(native_handle, hwnd_topmost, left, top, width, height, swp_showwindow):
        logger.warning("Could not place vision overlay on monitor %s", monitor)
        return

    class Rect(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    actual = Rect()
    if user32.GetWindowRect(native_handle, ctypes.byref(actual)):
        logger.debug(
            "Vision overlay requested=%s actual=(%d, %d, %d, %d)",
            monitor,
            actual.left,
            actual.top,
            actual.right - actual.left,
            actual.bottom - actual.top,
        )


def _monitor_geometries(virtual: tuple[int, int, int, int]) -> list[tuple[int, int, int, int]]:
    if not hasattr(ctypes, "windll"):
        return [virtual]

    class Rect(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    monitors: list[tuple[int, int, int, int]] = []
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(Rect),
        ctypes.c_longlong,
    )

    @callback_type
    def collect(_monitor, _dc, rect_pointer, _data) -> int:  # noqa: ANN001
        rect = rect_pointer.contents
        monitors.append((rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top))
        return 1

    ctypes.windll.user32.EnumDisplayMonitors(None, None, collect, 0)
    return monitors or [virtual]


def _virtual_screen_geometry(screenshot: Image.Image) -> tuple[int, int, int, int]:
    width, height = screenshot.size
    if not hasattr(ctypes, "windll"):
        return 0, 0, width, height
    user32 = ctypes.windll.user32
    left = int(user32.GetSystemMetrics(76))
    top = int(user32.GetSystemMetrics(77))
    system_width = int(user32.GetSystemMetrics(78))
    system_height = int(user32.GetSystemMetrics(79))
    if system_width == width and system_height == height:
        return left, top, width, height
    return 0, 0, width, height


def _enable_dpi_awareness(logger: logging.Logger) -> None:
    if not hasattr(ctypes, "windll"):
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not change DPI awareness: %s", exc)
