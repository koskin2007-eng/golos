from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from voice_input.config import ConfigManager, DEFAULT_CONFIG_DATA, PremiumSettings, deep_merge
from voice_input.diagnostics import collect_diagnostics
from voice_input.env_file import OPENAI_API_KEY_NAME, default_env_path, env_value_exists, normalize_openai_api_key, set_env_value
from voice_input.logger import DEFAULT_LOG_PATH
from voice_input.paths import resolve_runtime_path
from voice_input.premium import (
    PREMIUM_KEY_NAME,
    check_premium_balance,
    normalize_premium_key,
    premium_env_value_exists,
    premium_key_from_env,
)
from voice_input.remote_actions import complete_remote_action, fetch_remote_actions
from voice_input.restart import write_restart_request
from voice_input.shortcuts import is_windows, shortcut_status, sync_shortcuts
from voice_input.support import create_support_package, open_support_package, support_token_from_env, upload_support_package
from voice_input.updater import PreparedUpdate, UpdateInfo, check_for_update, prepare_update_install, write_update_install_request
from voice_input.version import APP_VERSION


COLORS = {
    "bg": "#fbfbef",
    "panel": "#ffffff",
    "soft": "#f4f9e8",
    "nav": "#164e2e",
    "green": "#16a34a",
    "green_dark": "#0f7a3a",
    "yellow": "#facc15",
    "yellow_soft": "#fff7c2",
    "ink": "#172112",
    "muted": "#5b6b4e",
    "border": "#d9e3c4",
}


LANGUAGE_OPTIONS = {
    "Русский": "ru",
    "Английский": "en",
    "Авто": "auto",
}


PROFILE_HELP_TEXT = {
    "base": (
        "База: распознавание выполняется на вашем компьютере локальной моделью. "
        "Аудио не отправляется в интернет. Это базовые настройки с нормальным балансом скорости и качества."
    ),
    "small": (
        "Смолл: распознавание выполняется на вашем компьютере локальной моделью. "
        "Работает медленнее базы, но обычно качественнее распознаёт русский текст."
    ),
    "tiny": (
        "Тини: распознавание выполняется на вашем компьютере локальной моделью. "
        "Это самый быстрый вариант, но качество распознавания заметно хуже."
    ),
    "openai": (
        "OpenAI: аудио отправляется через интернет в OpenAI и распознаётся GPT-моделью. "
        "Обычно лучше подходит для сложной диктовки, но требует ключ OpenAI и интернет."
    ),
    "premium": (
        "Премиум: аудио отправляется через интернет на сервер Голос, а сервер распознаёт его через OpenAI. "
        "Подходит для пользователей без собственного OpenAI API-ключа."
    ),
}

PROFILE_LABELS = {
    "base": "База - локально, базовые настройки",
    "small": "Смолл - локально, медленнее, качественнее",
    "tiny": "Тини - локально, быстро, качество хуже",
    "openai": "OpenAI - через интернет, с помощью GPT",
    "premium": "Премиум Голос - через наш сервер",
}

PROFILE_ORDER = ("base", "small", "tiny", "openai", "premium")

LOCAL_MODEL_NAMES = {
    "base": "Локальная модель Whisper base",
    "small": "Локальная модель Whisper small",
    "tiny": "Локальная модель Whisper tiny",
}


class SettingsWindow:
    def __init__(self, config_path: str | Path = "config.yaml") -> None:
        self.config_manager = ConfigManager(config_path)
        self.raw_config = self.config_manager._read_yaml_mapping()
        self.config = deep_merge(DEFAULT_CONFIG_DATA, self.raw_config)

        self.root = tk.Tk()
        self.root.title("Голос - настройки")
        self.root.geometry("900x740")
        self.root.minsize(820, 700)
        self.root.configure(bg=COLORS["bg"])

        self.hotkey_var = tk.StringVar(value=str(self.config.get("hotkey") or "F8"))
        self.profile_var = tk.StringVar(value=self._profile_label(str(self.config.get("recognition_profile") or "base")))
        self.language_var = tk.StringVar(value=self._label_for_language(str(self.config.get("language") or "ru")))
        self.openai_model_var = tk.StringVar(value=str((self.config.get("openai") or {}).get("model") or "gpt-4o-mini-transcribe"))
        self.openai_key_var = tk.StringVar(value="")
        self.openai_key_status_var = tk.StringVar(value=self._openai_key_status_text())
        premium = self.config.get("premium") or {}
        self.premium_server_url_var = tk.StringVar(value=str(premium.get("server_url") or "https://golos.msgcrm.ru"))
        self.premium_key_var = tk.StringVar(value="")
        self.premium_key_status_var = tk.StringVar(value=self._premium_key_status_text())
        self.premium_balance_var = tk.StringVar(value="Баланс не проверялся.")
        text_correction = self.config.get("text_correction") or {}
        self.text_correction_enabled_var = tk.BooleanVar(value=bool(text_correction.get("enabled", False)))
        self.text_correction_model_var = tk.StringVar(value=str(text_correction.get("model") or "gpt-5.4-mini"))
        self.beep_var = tk.BooleanVar(value=bool((self.config.get("feedback") or {}).get("beep_on_recording", True)))
        self.autostart_var = tk.BooleanVar(value=bool((self.config.get("startup") or {}).get("run_on_windows_startup", False)))
        self.status_var = tk.StringVar(value="Настройки загружены")
        self.profile_info_var = tk.StringVar()
        self.recognition_model_info_var = tk.StringVar()
        self.correction_model_info_var = tk.StringVar()
        self.update_status_var = tk.StringVar(value="Обновления ещё не проверялись.")
        self.update_detail_var = tk.StringVar(value="")
        self.shortcut_status_var = tk.StringVar(value=self._shortcut_status_text())
        support = self.config.get("support") or {}
        self.support_server_url_var = tk.StringVar(value=str(support.get("server_url") or ""))
        self.support_status_var = tk.StringVar(value=self._support_status_text())
        self.latest_update_info: UpdateInfo | None = None
        self.download_update_button: ttk.Button | None = None

        self._configure_styles()
        self._build()

    def run(self) -> None:
        self.root.mainloop()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure("Soft.TFrame", background=COLORS["soft"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["ink"], font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=COLORS["nav"], foreground="white", font=("Segoe UI", 26, "bold"))
        style.configure("Subtitle.TLabel", background=COLORS["nav"], foreground="#d9f99d", font=("Segoe UI", 10))
        style.configure("Heading.TLabel", background=COLORS["bg"], foreground=COLORS["ink"], font=("Segoe UI", 18, "bold"))
        style.configure("Section.TLabel", background=COLORS["panel"], foreground=COLORS["ink"], font=("Segoe UI", 13, "bold"))
        style.configure("Panel.TLabel", background=COLORS["panel"], foreground=COLORS["ink"], font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=(14, 8), background=COLORS["yellow_soft"], foreground=COLORS["ink"])
        style.map(
            "TButton",
            background=[("active", COLORS["yellow"]), ("pressed", COLORS["yellow"])],
            foreground=[("active", COLORS["ink"]), ("pressed", COLORS["ink"]), ("disabled", COLORS["muted"])],
        )
        style.configure("Accent.TButton", background=COLORS["green"], foreground="white")
        style.map(
            "Accent.TButton",
            background=[("active", COLORS["green_dark"]), ("pressed", COLORS["green_dark"])],
            foreground=[("active", "white"), ("pressed", "white"), ("disabled", "#d8ead8")],
        )
        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 10), font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", COLORS["green"])], foreground=[("selected", "white")])
        style.configure("TCheckbutton", background=COLORS["panel"], foreground=COLORS["ink"], font=("Segoe UI", 10))
        style.configure("TCombobox", padding=(8, 6))

    def _build(self) -> None:
        header = tk.Frame(self.root, bg=COLORS["nav"], height=88)
        header.pack(fill="x")
        header.pack_propagate(False)

        mark = tk.Canvas(header, width=44, height=44, bg=COLORS["nav"], highlightthickness=0)
        mark.pack(side="left", padx=(24, 14), pady=22)
        mark.create_rectangle(5, 5, 39, 39, fill=COLORS["green"], outline=COLORS["yellow"], width=2)
        mark.create_oval(18, 8, 26, 26, fill="white", outline="white")
        mark.create_rectangle(20, 26, 24, 36, fill="white", outline="white")
        mark.create_line(13, 36, 31, 36, fill="white", width=3)

        title_box = tk.Frame(header, bg=COLORS["nav"])
        title_box.pack(side="left", fill="y", pady=16)
        ttk.Label(title_box, text="Голос", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Голосовой ввод Windows", style="Subtitle.TLabel").pack(anchor="w")

        status = tk.Label(
            header,
            text="F8 готова",
            bg="#246b3f",
            fg="white",
            padx=18,
            pady=7,
            font=("Segoe UI", 10, "bold"),
        )
        status.pack(side="right", padx=28)

        body = ttk.Frame(self.root, padding=(24, 20, 24, 16))
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Настройки", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(body, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", pady=(2, 14))

        notebook = ttk.Notebook(body)
        notebook.pack(fill="both", expand=True)

        main_tab = ttk.Frame(notebook, padding=18)
        recognition_tab = ttk.Frame(notebook, padding=18)
        diagnostics_tab = ttk.Frame(notebook, padding=18)
        updates_tab = ttk.Frame(notebook, padding=18)

        notebook.add(main_tab, text="Главное")
        notebook.add(recognition_tab, text="Распознавание")
        notebook.add(diagnostics_tab, text="Диагностика")
        notebook.add(updates_tab, text="Обновления")

        self._build_main_tab(main_tab)
        self._build_recognition_tab(recognition_tab)
        self._build_diagnostics_tab(diagnostics_tab)
        self._build_updates_tab(updates_tab)

        footer = ttk.Frame(body)
        footer.pack(fill="x", pady=(16, 0))
        ttk.Button(footer, text="Перезапустить Голос", command=self._request_restart).pack(side="left")
        ttk.Button(footer, text="Создать ярлыки Windows", command=self._create_shortcuts_now).pack(side="left", padx=(10, 0))
        ttk.Button(footer, text="Сохранить", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(footer, text="Закрыть", command=self.root.destroy).pack(side="right", padx=(0, 10))

    def _panel(self, parent: ttk.Frame) -> ttk.Frame:
        panel = tk.Frame(parent, bg=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1)
        panel.pack(fill="x", pady=(0, 14))
        inner = ttk.Frame(panel, padding=16, style="Panel.TFrame")
        inner.pack(fill="both", expand=True)
        return inner

    def _build_main_tab(self, parent: ttk.Frame) -> None:
        panel = self._panel(parent)
        ttk.Label(panel, text="Основное", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self._field(panel, 1, "Горячая клавиша", ttk.Entry(panel, textvariable=self.hotkey_var, width=24))
        self._field(panel, 2, "Язык", ttk.Combobox(panel, textvariable=self.language_var, values=list(LANGUAGE_OPTIONS), state="readonly", width=22))
        ttk.Checkbutton(panel, text="Звуковой сигнал при начале и окончании записи", variable=self.beep_var).grid(row=3, column=1, sticky="w", pady=8)
        autostart = ttk.Checkbutton(panel, text="Запускать Голос вместе с Windows", variable=self.autostart_var)
        autostart.grid(row=4, column=1, sticky="w", pady=8)
        if not is_windows():
            autostart.state(["disabled"])
        tk.Label(
            panel,
            textvariable=self.shortcut_status_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=560,
        ).grid(row=5, column=1, sticky="w", pady=(2, 8))
        panel.columnconfigure(1, weight=1)

    def _build_recognition_tab(self, parent: ttk.Frame) -> None:
        panel = self._panel(parent)
        profile_ids = [str(name) for name in (self.config.get("profiles") or {})]
        profiles = [self._profile_label(name) for name in self._ordered_profile_ids(profile_ids)]
        ttk.Label(panel, text="Распознавание", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        profile_combo = ttk.Combobox(panel, textvariable=self.profile_var, values=profiles, state="readonly", width=46)
        self._field(panel, 1, "Профиль", profile_combo)

        recognition_value = self._readonly_value_label(panel, self.recognition_model_info_var, wraplength=540)
        self._field(panel, 2, "Распознавание", recognition_value)

        self.text_correction_check = ttk.Checkbutton(
            panel,
            text="GPT исправляет ошибки после распознавания",
            variable=self.text_correction_enabled_var,
            command=self._refresh_recognition_profile_ui,
        )
        self.text_correction_check.grid(row=3, column=1, sticky="w", pady=(10, 8))
        correction_value = self._readonly_value_label(panel, self.correction_model_info_var, wraplength=540)
        self._field(panel, 4, "Исправление", correction_value)

        openai_key_box = ttk.Frame(panel, style="Panel.TFrame")
        ttk.Entry(openai_key_box, textvariable=self.openai_key_var, show="*", width=46).pack(side="left", fill="x", expand=True)
        ttk.Button(openai_key_box, text="Очистить поле", command=lambda: self.openai_key_var.set("")).pack(side="left", padx=(8, 0))
        self._field(panel, 5, "OpenAI API-ключ", openai_key_box)
        tk.Label(
            panel,
            textvariable=self.openai_key_status_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=590,
        ).grid(row=6, column=1, sticky="w", pady=(0, 8))

        premium_server_box = ttk.Entry(panel, textvariable=self.premium_server_url_var, width=46)
        self._field(panel, 7, "Сервер Премиум", premium_server_box)

        premium_key_box = ttk.Frame(panel, style="Panel.TFrame")
        ttk.Entry(premium_key_box, textvariable=self.premium_key_var, show="*", width=34).pack(side="left", fill="x", expand=True)
        ttk.Button(premium_key_box, text="Очистить поле", command=lambda: self.premium_key_var.set("")).pack(side="left", padx=(8, 0))
        ttk.Button(premium_key_box, text="Проверить баланс", command=self._check_premium_balance).pack(side="left", padx=(8, 0))
        self._field(panel, 8, "Премиум-ключ Голос", premium_key_box)
        tk.Label(
            panel,
            textvariable=self.premium_key_status_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=590,
        ).grid(row=9, column=1, sticky="w", pady=(0, 4))
        tk.Label(
            panel,
            textvariable=self.premium_balance_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=590,
        ).grid(row=10, column=1, sticky="w", pady=(0, 8))

        info = tk.Label(
            panel,
            textvariable=self.profile_info_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=590,
        )
        info.grid(row=11, column=1, sticky="w", pady=(10, 0))
        panel.columnconfigure(1, weight=1)
        profile_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_recognition_profile_ui())
        self._refresh_recognition_profile_ui()

    def _build_diagnostics_tab(self, parent: ttk.Frame) -> None:
        panel = self._panel(parent)
        ttk.Label(panel, text="Диагностика", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self._field(
            panel,
            1,
            "Сервер поддержки",
            ttk.Entry(panel, textvariable=self.support_server_url_var, width=54),
        )
        tk.Label(
            panel,
            textvariable=self.support_status_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=590,
        ).grid(row=2, column=1, sticky="w", pady=(0, 12))

        buttons = ttk.Frame(panel, style="Panel.TFrame")
        buttons.grid(row=3, column=1, sticky="w", pady=(4, 0))
        ttk.Button(buttons, text="Открыть лог", command=self._open_log).pack(side="left")
        ttk.Button(buttons, text="Собрать диагностику", style="Accent.TButton", command=self._collect_diagnostics).pack(side="left", padx=(10, 0))
        ttk.Button(buttons, text="Отправить диагностику", command=self._prepare_support_request).pack(side="left", padx=(10, 0))
        ttk.Button(buttons, text="Проверить запросы поддержки", command=self._check_support_actions).pack(side="left", padx=(10, 0))
        panel.columnconfigure(1, weight=1)

    def _build_updates_tab(self, parent: ttk.Frame) -> None:
        panel = self._panel(parent)
        ttk.Label(panel, text="Обновления", style="Section.TLabel").pack(anchor="w", pady=(0, 12))
        tk.Label(
            panel,
            text=f"Текущая версия: {APP_VERSION}",
            bg=COLORS["panel"],
            fg=COLORS["ink"],
            justify="left",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 10))
        tk.Label(
            panel,
            textvariable=self.update_status_var,
            bg=COLORS["panel"],
            fg=COLORS["ink"],
            justify="left",
            wraplength=560,
        ).pack(anchor="w", pady=(0, 8))
        tk.Label(
            panel,
            textvariable=self.update_detail_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=620,
        ).pack(anchor="w", pady=(0, 14))

        buttons = ttk.Frame(panel, style="Panel.TFrame")
        buttons.pack(anchor="w")
        ttk.Button(buttons, text="Проверить обновления", style="Accent.TButton", command=self._check_updates).pack(side="left")
        self.download_update_button = ttk.Button(buttons, text="Скачать и установить", command=self._download_update)
        self.download_update_button.pack(side="left", padx=(10, 0))
        self.download_update_button.state(["disabled"])
        ttk.Button(buttons, text="Открыть GitHub", command=self._open_github).pack(side="left", padx=(10, 0))

    def _field(self, parent: ttk.Frame, row: int, label: str, widget: tk.Widget) -> ttk.Label:
        label_widget = ttk.Label(parent, text=label, style="Panel.TLabel")
        label_widget.grid(row=row, column=0, sticky="w", padx=(0, 18), pady=8)
        widget.grid(row=row, column=1, sticky="w", pady=8)
        return label_widget

    def _readonly_value_label(self, parent: ttk.Frame, textvariable: tk.StringVar, wraplength: int) -> tk.Label:
        return tk.Label(
            parent,
            textvariable=textvariable,
            bg=COLORS["soft"],
            fg=COLORS["ink"],
            justify="left",
            anchor="w",
            padx=12,
            pady=8,
            wraplength=wraplength,
            font=("Segoe UI", 10),
        )

    def _refresh_recognition_profile_ui(self) -> None:
        profile = self._profile_id_from_label(self.profile_var.get())
        correction_enabled = bool(self.text_correction_enabled_var.get())

        self.recognition_model_info_var.set(self._recognition_model_text(profile))
        self.correction_model_info_var.set(self._correction_model_text(correction_enabled))

        help_text = PROFILE_HELP_TEXT.get(profile, "Выберите профиль распознавания.")
        if correction_enabled:
            help_text += " После распознавания текст дополнительно отправляется в GPT для исправления очевидных ошибок."
        self.profile_info_var.set(help_text)

    def _save(self) -> None:
        hotkey = self.hotkey_var.get().strip()
        profile = self._profile_id_from_label(self.profile_var.get())
        language = LANGUAGE_OPTIONS.get(self.language_var.get(), "ru")
        openai_model = self.openai_model_var.get().strip()
        openai_key = normalize_openai_api_key(self.openai_key_var.get())
        premium_key = normalize_premium_key(self.premium_key_var.get(), PREMIUM_KEY_NAME)
        text_correction_model = self.text_correction_model_var.get().strip()

        if not hotkey:
            messagebox.showerror("Голос", "Укажите горячую клавишу.")
            return
        if not profile:
            messagebox.showerror("Голос", "Выберите профиль распознавания.")
            return
        if profile not in (self.config.get("profiles") or {}):
            messagebox.showerror("Голос", "Такого профиля нет в config.yaml.")
            return
        if profile == "openai" and not openai_model:
            messagebox.showerror("Голос", "Укажите модель распознавания GPT.")
            return
        if profile == "premium" and not self.premium_server_url_var.get().strip():
            messagebox.showerror("Голос", "Укажите сервер Голос Премиум.")
            return
        if self.text_correction_enabled_var.get() and not text_correction_model:
            messagebox.showerror("Голос", "Укажите модель исправления.")
            return
        if (profile == "openai" or self.text_correction_enabled_var.get()) and not (openai_key or self._openai_key_exists()):
            messagebox.showerror("Голос", "Для OpenAI-режима вставьте API-ключ OpenAI на вкладке распознавания.")
            return
        if profile == "premium" and not (premium_key or self._premium_key_exists()):
            messagebox.showerror("Голос", "Для премиум-режима вставьте премиум-ключ Голос.")
            return

        try:
            openai_key_saved = self._save_openai_key_if_needed(openai_key)
            premium_key_saved = self._save_premium_key_if_needed(premium_key)
        except ValueError as exc:
            messagebox.showerror("Голос", str(exc))
            return
        except OSError as exc:
            messagebox.showerror("Голос", f"Не удалось сохранить ключ: {exc}")
            return

        raw = self.config_manager._read_yaml_mapping()
        raw["hotkey"] = hotkey
        raw["language"] = language
        raw["recognition_profile"] = profile
        raw.setdefault("openai", {})["model"] = openai_model
        raw.setdefault("premium", {})["server_url"] = self.premium_server_url_var.get().strip()
        raw.setdefault("premium", {})["license_key_env"] = PREMIUM_KEY_NAME
        raw.setdefault("text_correction", {})["enabled"] = bool(self.text_correction_enabled_var.get())
        raw.setdefault("text_correction", {})["model"] = text_correction_model
        raw.setdefault("feedback", {})["beep_on_recording"] = bool(self.beep_var.get())
        raw.setdefault("startup", {})["run_on_windows_startup"] = bool(self.autostart_var.get())
        raw.setdefault("support", {})["server_url"] = self.support_server_url_var.get().strip()
        raw.setdefault("support", {})["token_env"] = str((self.config.get("support") or {}).get("token_env") or "GOLOS_SUPPORT_TOKEN")

        self.config_manager._write_yaml_mapping(raw)
        self.raw_config = raw
        self.config = deep_merge(DEFAULT_CONFIG_DATA, raw)
        self._apply_shortcuts()
        self.support_status_var.set(self._support_status_text())
        if openai_key_saved:
            self.openai_key_status_var.set(self._openai_key_status_text())
        if premium_key_saved:
            self.premium_key_status_var.set(self._premium_key_status_text())
        self.status_var.set("Сохранено. Для применения горячей клавиши и профиля перезапустите Голос.")
        message = "Настройки сохранены."
        if openai_key_saved:
            message += "\n\nOpenAI API-ключ сохранён локально на этом компьютере."
        if premium_key_saved:
            message += "\n\nПремиум-ключ Голос сохранён локально на этом компьютере."
        messagebox.showinfo("Голос", message)

    def _apply_shortcuts(self) -> None:
        try:
            sync_shortcuts(self.config_manager.path, bool(self.autostart_var.get()))
            self.shortcut_status_var.set(self._shortcut_status_text())
        except Exception as exc:  # noqa: BLE001
            self.shortcut_status_var.set("Не удалось обновить ярлыки Windows.")
            messagebox.showwarning("Голос", f"Настройки сохранены, но ярлыки Windows не обновились: {exc}")

    def _create_shortcuts_now(self) -> None:
        try:
            sync_shortcuts(self.config_manager.path, bool(self.autostart_var.get()))
            self.shortcut_status_var.set(self._shortcut_status_text())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Голос", f"Не удалось создать ярлыки Windows: {exc}")
            return
        messagebox.showinfo("Голос", "Ярлык в меню Пуск создан. Автозапуск обновлён по текущей галочке.")

    def _request_restart(self) -> None:
        if not messagebox.askyesno("Голос", "Перезапустить Голос сейчас? Несохранённые изменения в этом окне не применятся."):
            return
        try:
            write_restart_request()
        except OSError as exc:
            messagebox.showerror("Голос", f"Не удалось отправить команду перезапуска: {exc}")
            return
        self.status_var.set("Команда перезапуска отправлена.")
        messagebox.showinfo("Голос", "Голос перезапустится через несколько секунд.")
        self.root.destroy()

    def _shortcut_status_text(self) -> str:
        if not is_windows():
            return "Автозапуск доступен только в Windows."
        status = shortcut_status()
        start_menu = "есть в меню Пуск" if status.start_menu_exists else "ярлык в меню Пуск будет создан при сохранении"
        startup = "автозапуск включён" if status.startup_exists else "автозапуск выключен"
        return f"{start_menu}; {startup}."

    def _support_status_text(self) -> str:
        server_url = self.support_server_url_var.get().strip() if hasattr(self, "support_server_url_var") else ""
        if server_url:
            return "Кнопка «Отправить диагностику» отправит безопасный архив на этот сервер. Аудио, модели и ключи не входят в архив."
        return "Если сервер не указан, кнопка откроет GitHub-обращение и папку с ZIP-архивом для ручной отправки."

    def _openai_key_exists(self) -> bool:
        return env_value_exists(default_env_path(), OPENAI_API_KEY_NAME) or bool(os.getenv(OPENAI_API_KEY_NAME))

    def _openai_key_status_text(self) -> str:
        if env_value_exists(default_env_path(), OPENAI_API_KEY_NAME):
            return "Ключ OpenAI сохранён локально. Чтобы заменить его, вставьте новый ключ и нажмите «Сохранить»."
        if os.getenv(OPENAI_API_KEY_NAME):
            return "Ключ OpenAI найден в переменных Windows. Можно вставить новый ключ, чтобы сохранить его локально."
        return "Ключ OpenAI не сохранён. Вставьте ключ сюда и нажмите «Сохранить»."

    def _save_openai_key_if_needed(self, openai_key: str) -> bool:
        if not openai_key:
            return False
        if any(ch.isspace() for ch in openai_key):
            raise ValueError("OpenAI API-ключ не должен содержать пробелы или переносы строк.")
        if len(openai_key) < 20:
            raise ValueError("OpenAI API-ключ выглядит слишком коротким. Проверьте, что ключ скопирован полностью.")
        set_env_value(default_env_path(), OPENAI_API_KEY_NAME, openai_key)
        os.environ[OPENAI_API_KEY_NAME] = openai_key
        self.openai_key_var.set("")
        return True

    def _premium_key_exists(self) -> bool:
        return premium_env_value_exists(self._premium_settings_from_ui())

    def _premium_key_status_text(self) -> str:
        if premium_env_value_exists(self._premium_settings_from_ui()):
            return "Премиум-ключ Голос сохранён локально. Чтобы заменить его, вставьте новый ключ и нажмите «Сохранить»."
        return "Премиум-ключ не сохранён. Его можно получить после оплаты пакета минут и вставить сюда."

    def _save_premium_key_if_needed(self, premium_key: str) -> bool:
        if not premium_key:
            return False
        if any(ch.isspace() for ch in premium_key):
            raise ValueError("Премиум-ключ не должен содержать пробелы или переносы строк.")
        if len(premium_key) < 20:
            raise ValueError("Премиум-ключ выглядит слишком коротким. Проверьте, что ключ скопирован полностью.")
        set_env_value(default_env_path(), PREMIUM_KEY_NAME, premium_key)
        os.environ[PREMIUM_KEY_NAME] = premium_key
        self.premium_key_var.set("")
        return True

    def _check_premium_balance(self) -> None:
        self.premium_balance_var.set("Проверяю баланс...")

        def worker() -> None:
            try:
                balance = check_premium_balance(self._premium_settings_from_ui())
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: self.premium_balance_var.set(f"Не удалось проверить баланс: {exc}"))
                return
            self.root.after(
                0,
                lambda: self.premium_balance_var.set(
                    f"Осталось {balance.balance_minutes:.1f} мин. Начислено {balance.total_granted_minutes:.1f} мин."
                ),
            )

        threading.Thread(target=worker, name="check-premium-balance", daemon=True).start()

    def _premium_settings_from_ui(self) -> PremiumSettings:
        premium = self.config.get("premium") or {}
        return PremiumSettings(
            server_url=self.premium_server_url_var.get().strip() or str(premium.get("server_url") or "https://golos.msgcrm.ru"),
            license_key_env=PREMIUM_KEY_NAME,
            model=str(premium.get("model") or "gpt-4o-mini-transcribe"),
        )

    def _open_log(self) -> None:
        path = resolve_runtime_path(DEFAULT_LOG_PATH)
        if path.exists():
            os.startfile(str(path))  # noqa: S606 - Windows desktop helper.
        else:
            messagebox.showinfo("Голос", "Лог пока не создан.")

    def _collect_diagnostics(self) -> None:
        archive_path = collect_diagnostics(self.config_manager.path, resolve_runtime_path(DEFAULT_LOG_PATH))
        self.status_var.set(f"Диагностика сохранена: {archive_path.name}")
        os.startfile(str(archive_path.parent))  # noqa: S606 - Windows desktop helper.

    def _prepare_support_request(self) -> None:
        try:
            package = create_support_package(self.config_manager.path, resolve_runtime_path(DEFAULT_LOG_PATH))
            support = self.config.get("support") or {}
            server_url = self.support_server_url_var.get().strip() or str(support.get("server_url") or "").strip()
            premium_key = premium_key_from_env(self._premium_settings_from_ui())
            if not server_url and premium_key:
                server_url = self._premium_settings_from_ui().server_url
            if server_url:
                result = upload_support_package(
                    package,
                    server_url,
                    support_token_from_env(str(support.get("token_env") or "GOLOS_SUPPORT_TOKEN")),
                    metadata={
                        "profile": str(self.config.get("recognition_profile") or ""),
                        "backend": str(self.config.get("backend") or ""),
                    },
                    premium_key=premium_key,
                )
                message = result.message
            else:
                open_support_package(package)
                message = "Открыл GitHub и папку с архивом. Прикрепите ZIP-файл к обращению."
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Голос", f"Не удалось подготовить обращение: {exc}")
            return
        self.status_var.set(f"Диагностика готова: {package.archive_path.name}")
        messagebox.showinfo("Голос", message)

    def _check_support_actions(self) -> None:
        self.status_var.set("Проверяю запросы поддержки...")

        def worker() -> None:
            try:
                actions = fetch_remote_actions(self._premium_settings_from_ui())
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: messagebox.showerror("Голос", f"Не удалось проверить запросы поддержки: {exc}"))
                self.root.after(0, lambda: self.status_var.set("Не удалось проверить запросы поддержки."))
                return
            self.root.after(0, lambda: self._show_support_actions(actions))

        threading.Thread(target=worker, name="check-support-actions", daemon=True).start()

    def _show_support_actions(self, actions) -> None:  # noqa: ANN001
        if not actions:
            self.status_var.set("Запросов поддержки нет.")
            messagebox.showinfo("Голос", "Запросов поддержки нет.")
            return

        for action in actions:
            if action.action_type == "diagnostics_request":
                question = action.message or "Поддержка Голос просит отправить диагностику. Отправить сейчас?"
                if not messagebox.askyesno("Голос: запрос поддержки", question):
                    complete_remote_action(self._premium_settings_from_ui(), action.action_id, "declined", "Пользователь отказался отправлять диагностику.")
                    continue
                try:
                    package = create_support_package(self.config_manager.path, resolve_runtime_path(DEFAULT_LOG_PATH))
                    result = upload_support_package(
                        package,
                        self._premium_settings_from_ui().server_url,
                        premium_key=premium_key_from_env(self._premium_settings_from_ui()),
                        metadata={
                            "profile": str(self.config.get("recognition_profile") or ""),
                            "backend": str(self.config.get("backend") or ""),
                        },
                    )
                    complete_remote_action(self._premium_settings_from_ui(), action.action_id, "done", f"Диагностика отправлена: {result.report_id}")
                    messagebox.showinfo("Голос", result.message)
                except Exception as exc:  # noqa: BLE001
                    complete_remote_action(self._premium_settings_from_ui(), action.action_id, "error", str(exc))
                    messagebox.showerror("Голос", f"Не удалось отправить диагностику: {exc}")
            elif action.action_type == "update_suggestion":
                messagebox.showinfo("Голос", action.message or "Поддержка предлагает проверить обновления Голос.")
                complete_remote_action(self._premium_settings_from_ui(), action.action_id, "seen", "Пользователь увидел уведомление.")
        self.status_var.set("Запросы поддержки обработаны.")

    def _check_updates(self) -> None:
        self.update_status_var.set("Проверяю обновления...")
        self.update_detail_var.set("")
        if self.download_update_button is not None:
            self.download_update_button.state(["disabled"])

        def worker() -> None:
            try:
                result = check_for_update()
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: self._show_update_error(exc))
                return
            self.root.after(0, lambda: self._show_update_result(result))

        threading.Thread(target=worker, name="check-updates", daemon=True).start()

    def _show_update_error(self, exc: Exception) -> None:
        self.latest_update_info = None
        self.update_status_var.set("Не удалось проверить обновления.")
        self.update_detail_var.set(str(exc))
        if self.download_update_button is not None:
            self.download_update_button.state(["disabled"])

    def _show_update_result(self, result) -> None:  # noqa: ANN001
        self.latest_update_info = result.info
        self.update_status_var.set(result.message)
        if result.info is not None:
            self.update_detail_var.set(f"Последняя версия: {result.latest_version}. Файл: {result.info.asset}.")
        if self.download_update_button is not None:
            self.download_update_button.state(["!disabled"] if result.update_available else ["disabled"])

    def _download_update(self) -> None:
        if self.latest_update_info is None:
            return
        info = self.latest_update_info
        if not messagebox.askyesno(
            "Голос",
            f"Скачать и установить версию {info.version}? Голос закроется и запустится заново после обновления.",
        ):
            return
        self.update_status_var.set(f"Скачиваю {info.asset}...")
        if self.download_update_button is not None:
            self.download_update_button.state(["disabled"])

        def worker() -> None:
            try:
                prepared = prepare_update_install(info)
                write_update_install_request(prepared)
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: self._show_update_error(exc))
                return
            self.root.after(0, lambda: self._show_download_result(prepared))

        threading.Thread(target=worker, name="download-update", daemon=True).start()

    def _show_download_result(self, prepared: PreparedUpdate) -> None:
        self.update_status_var.set("Обновление скачано и проверено.")
        self.update_detail_var.set(str(prepared.package_path))
        messagebox.showinfo("Голос", "Обновление готово. Голос закроется, заменит файлы и запустится заново.")
        self.root.destroy()

    def _open_github(self) -> None:
        os.startfile("https://github.com/koskin2007-eng/golos")  # noqa: S606 - Windows desktop helper.

    def _label_for_language(self, language: str) -> str:
        for label, code in LANGUAGE_OPTIONS.items():
            if code == language:
                return label
        return "Русский"

    def _ordered_profile_ids(self, profile_ids: list[str]) -> list[str]:
        ordered = [profile for profile in PROFILE_ORDER if profile in profile_ids]
        ordered.extend(sorted(profile for profile in profile_ids if profile not in PROFILE_ORDER))
        return ordered

    def _profile_label(self, profile: str) -> str:
        return PROFILE_LABELS.get(profile, profile)

    def _profile_id_from_label(self, label: str) -> str:
        reverse = {display: profile for profile, display in PROFILE_LABELS.items()}
        return reverse.get(label.strip(), label.strip())

    def _recognition_model_text(self, profile: str) -> str:
        if profile == "openai":
            return f"Через интернет с помощью OpenAI: {self.openai_model_var.get()}."
        if profile == "premium":
            return f"Через сервер Голос Премиум: {self.premium_server_url_var.get()}."
        return f"{LOCAL_MODEL_NAMES.get(profile, 'Локальная модель')}. Работает на вашем Windows-компьютере без отправки аудио в интернет."

    def _correction_model_text(self, enabled: bool) -> str:
        if enabled:
            return f"GPT исправляет готовый текст: {self.text_correction_model_var.get()}."
        return "Не используется. Текст вставляется сразу после распознавания."


def open_settings_window(config_path: str | Path = "config.yaml") -> None:
    SettingsWindow(config_path).run()
