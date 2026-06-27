from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path


class TrayController:
    def __init__(
        self,
        config_path: str | Path,
        log_path: str | Path,
        status_getter: Callable[[], str],
        on_exit: Callable[[], None],
        diagnostics_collector: Callable[[], Path] | None = None,
    ) -> None:
        self.config_path = Path(config_path).resolve()
        self.log_path = Path(log_path).resolve()
        self.status_getter = status_getter
        self.on_exit = on_exit
        self.diagnostics_collector = diagnostics_collector
        self._icon = None
        self._lock = threading.Lock()

    def run(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError as exc:
            raise RuntimeError("pystray and Pillow are required for tray mode. Run .\\run.ps1 first.") from exc

        def create_image():
            image = Image.new("RGB", (64, 64), "#0b1220")
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill="#0f766e", outline="#38bdf8", width=3)
            draw.ellipse((25, 14, 39, 38), fill="#ffffff")
            draw.rounded_rectangle((29, 36, 35, 49), radius=3, fill="#ffffff")
            draw.line((20, 49, 44, 49), fill="#ffffff", width=4)
            return image

        menu = pystray.Menu(
            pystray.MenuItem(lambda _item: f"Статус: {self.status_getter()}", None, enabled=False),
            pystray.MenuItem("Открыть настройки", lambda _icon, _item: self._open_path(self.config_path)),
            pystray.MenuItem("Открыть лог", lambda _icon, _item: self._open_path(self.log_path)),
            pystray.MenuItem("Собрать диагностику", self._collect_diagnostics, enabled=self.diagnostics_collector is not None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", self._exit),
        )
        self._icon = pystray.Icon("voice_input", create_image(), "Голос", menu)
        self._icon.run()

    def notify(self, title: str, message: str) -> None:
        with self._lock:
            icon = self._icon
        if icon is None:
            return
        try:
            icon.notify(message, title)
        except Exception:
            pass

    def update_menu(self) -> None:
        with self._lock:
            icon = self._icon
        if icon is not None:
            try:
                icon.update_menu()
            except Exception:
                pass

    def stop(self) -> None:
        with self._lock:
            icon = self._icon
        if icon is not None:
            icon.stop()

    def _exit(self, icon, item) -> None:  # noqa: ANN001
        self.on_exit()
        icon.stop()

    def _collect_diagnostics(self, icon, item) -> None:  # noqa: ANN001
        if self.diagnostics_collector is None:
            return

        def worker() -> None:
            try:
                archive_path = self.diagnostics_collector()
                self.notify("Голос", f"Диагностика сохранена: {archive_path.name}")
                os.startfile(str(archive_path.parent))  # noqa: S606 - Windows desktop helper.
            except Exception as exc:  # noqa: BLE001
                self.notify("Голос: ошибка", f"Не удалось собрать диагностику: {exc}")

        threading.Thread(target=worker, name="collect-diagnostics", daemon=True).start()

    @staticmethod
    def _open_path(path: Path) -> None:
        if path.exists():
            os.startfile(str(path))  # noqa: S606 - Windows desktop helper.
