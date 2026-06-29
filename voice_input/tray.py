from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from voice_input.branding import PUBLIC_SITE_URL, create_logo_image


class TrayController:
    def __init__(
        self,
        config_path: str | Path,
        log_path: str | Path,
        status_getter: Callable[[], str],
        on_exit: Callable[[], None],
        diagnostics_collector: Callable[[], Path] | None = None,
        support_request_creator: Callable[[], Path] | None = None,
        settings_opener: Callable[[], None] | None = None,
        restart_requester: Callable[[], None] | None = None,
    ) -> None:
        self.config_path = Path(config_path).resolve()
        self.log_path = Path(log_path).resolve()
        self.status_getter = status_getter
        self.on_exit = on_exit
        self.diagnostics_collector = diagnostics_collector
        self.support_request_creator = support_request_creator
        self.settings_opener = settings_opener
        self.restart_requester = restart_requester
        self._icon = None
        self._lock = threading.Lock()

    def run(self) -> None:
        try:
            import pystray
        except ImportError as exc:
            raise RuntimeError("pystray and Pillow are required for tray mode. Run .\\run.ps1 first.") from exc

        menu = pystray.Menu(
            pystray.MenuItem(lambda _item: f"Статус: {self.status_getter()}", None, enabled=False),
            pystray.MenuItem("Открыть настройки", self._open_settings),
            pystray.MenuItem("Сайт Голос", self._open_site),
            pystray.MenuItem("Перезапустить Голос", self._restart, enabled=self.restart_requester is not None),
            pystray.MenuItem("Открыть лог", lambda _icon, _item: self._open_path(self.log_path)),
            pystray.MenuItem("Собрать диагностику", self._collect_diagnostics, enabled=self.diagnostics_collector is not None),
            pystray.MenuItem("Отправить диагностику", self._prepare_support_request, enabled=self.support_request_creator is not None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", self._exit),
        )
        self._icon = pystray.Icon("voice_input", create_logo_image(64), "Голос", menu)
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

    def _restart(self, icon, item) -> None:  # noqa: ANN001
        if self.restart_requester is not None:
            self.restart_requester()
            return
        self._exit(icon, item)

    def _open_site(self, icon, item) -> None:  # noqa: ANN001
        self._open_url(PUBLIC_SITE_URL)

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

    def _prepare_support_request(self, icon, item) -> None:  # noqa: ANN001
        if self.support_request_creator is None:
            return

        def worker() -> None:
            try:
                archive_path = self.support_request_creator()
                self.notify("Голос", f"Диагностика готова: {archive_path.name}")
            except Exception as exc:  # noqa: BLE001
                self.notify("Голос: ошибка", f"Не удалось подготовить обращение: {exc}")

        threading.Thread(target=worker, name="prepare-support-request", daemon=True).start()

    def _open_settings(self, icon, item) -> None:  # noqa: ANN001
        if self.settings_opener is not None:
            self.settings_opener()
            return

        if getattr(sys, "frozen", False):
            command = [sys.executable, "--settings", "--config", str(self.config_path)]
        else:
            command = [sys.executable, "-m", "voice_input.app", "--settings", "--config", str(self.config_path)]

        subprocess.Popen(
            command,
            cwd=str(Path.cwd()),
            close_fds=True,
        )

    @staticmethod
    def _open_path(path: Path) -> None:
        if path.exists():
            os.startfile(str(path))  # noqa: S606 - Windows desktop helper.

    @staticmethod
    def _open_url(url: str) -> None:
        try:
            os.startfile(url)  # noqa: S606 - Windows desktop helper.
        except (AttributeError, OSError):
            import webbrowser

            webbrowser.open(url)
