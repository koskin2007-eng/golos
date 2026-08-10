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
    root.title("Голос — перевод экрана")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    geometry = f"{width}x{height}{left:+d}{top:+d}"
    root.geometry(geometry)
    root.configure(cursor="crosshair")
    root.attributes("-alpha", 0.28)

    # Keep the real desktop visible through the overlay. Rendering one very wide
    # ImageTk background can turn black on some multi-monitor Windows setups.
    canvas = tk.Canvas(
        root,
        width=width,
        height=height,
        background="black",
        highlightthickness=0,
        cursor="crosshair",
    )
    canvas.pack(fill="both", expand=True)
    canvas.create_text(
        width // 2,
        34,
        text="Выделите текст для перевода • Esc — отмена",
        fill="white",
        font=("Segoe UI", 13, "bold"),
    )

    state: dict[str, object] = {"start": None, "rectangle": None, "finished": False}

    def cancel(_event=None) -> None:  # noqa: ANN001
        if state["finished"]:
            return
        state["finished"] = True
        root.destroy()
        on_cancelled()

    def press(event: tk.Event) -> None:
        state["start"] = (event.x, event.y)
        rectangle = state.get("rectangle")
        if rectangle is not None:
            canvas.delete(rectangle)
        state["rectangle"] = canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="#facc15",
            width=3,
            fill="",
        )

    def drag(event: tk.Event) -> None:
        start = state.get("start")
        rectangle = state.get("rectangle")
        if start is None or rectangle is None:
            return
        start_x, start_y = start
        canvas.coords(rectangle, start_x, start_y, event.x, event.y)

    def release(event: tk.Event) -> None:
        start = state.get("start")
        if start is None or state["finished"]:
            return
        start_x, start_y = start
        x1, x2 = sorted((max(0, start_x), min(width, event.x)))
        y1, y2 = sorted((max(0, start_y), min(height, event.y)))
        if x2 - x1 < 12 or y2 - y1 < 12:
            return
        state["finished"] = True
        crop = screenshot.crop((x1, y1, x2, y2)).copy()
        root.destroy()
        on_selected(crop)

    root.bind("<Escape>", cancel)
    canvas.bind("<ButtonPress-1>", press)
    canvas.bind("<B1-Motion>", drag)
    canvas.bind("<ButtonRelease-1>", release)
    root.focus_force()
    root.mainloop()


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
