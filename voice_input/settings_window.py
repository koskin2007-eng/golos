from __future__ import annotations

import os
import threading
import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from voice_input.account import (
    DEFAULT_ACCOUNT_SERVER_URL,
    account_email_from_env,
    account_token_from_env,
    account_token_exists,
    clear_account_session,
    create_account_payment,
    fetch_account,
    login_account,
    logout_account,
    register_account,
    save_account_session,
)
from voice_input.branding import GITHUB_URL, PUBLIC_SITE_URL, asset_path, create_logo_image
from voice_input.config import ConfigManager, DEFAULT_CONFIG_DATA, PremiumSettings, deep_merge
from voice_input.diagnostics import collect_diagnostics
from voice_input.env_file import OPENAI_API_KEY_NAME, default_env_path, env_value_exists, normalize_openai_api_key, set_env_value
from voice_input.logger import DEFAULT_LOG_PATH
from voice_input.paths import resolve_runtime_path
from voice_input.premium import (
    PREMIUM_KEY_NAME,
    check_premium_balance,
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
        "Локальный базовый режим: распознавание выполняется на вашем компьютере. "
        "Аудио не отправляется в интернет. Это рабочий баланс скорости и качества."
    ),
    "small": (
        "Локальный улучшенный режим: распознавание выполняется на вашем компьютере. "
        "Работает медленнее базового, но обычно точнее распознаёт русский текст."
    ),
    "tiny": (
        "Локальный быстрый режим: распознавание выполняется на вашем компьютере. "
        "Это самый быстрый вариант, но качество распознавания ниже."
    ),
    "openai": (
        "OpenAI напрямую: аудио отправляется из этой программы в OpenAI по вашему личному API-ключу. "
        "Баланс Голос Премиум в этом режиме не списывается."
    ),
    "server": (
        "Сервер Голос: нужен интернет. Аудио отправляется на наш сервер, где распознаётся локальной моделью Голос. "
        "OpenAI и личный API-ключ в этом режиме не используются."
    ),
    "premium": (
        "Голос Премиум: аудио отправляется на сервер Голос, сервер распознаёт его через OpenAI "
        "и списывает минуты с вашего баланса."
    ),
}

PROFILE_LABELS = {
    "base": "Локально: базовый баланс",
    "small": "Локально: лучше, медленнее",
    "tiny": "Локально: быстро, качество ниже",
    "server": "Сервер Голос: без OpenAI",
    "openai": "OpenAI напрямую: свой API-ключ",
    "premium": "Голос Премиум: через наш сервер",
}

PROFILE_ORDER = ("base", "small", "tiny", "server", "openai", "premium")

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
        self.root.geometry("920x720")
        self.root.minsize(760, 560)
        self.root.configure(bg=COLORS["bg"])
        self._set_window_icon()
        self.logo_photo = None

        self.hotkey_var = tk.StringVar(value=str(self.config.get("hotkey") or "F8"))
        self.profile_var = tk.StringVar(value=self._profile_label(str(self.config.get("recognition_profile") or "base")))
        self.language_var = tk.StringVar(value=self._label_for_language(str(self.config.get("language") or "ru")))
        self.openai_model_var = tk.StringVar(value=str((self.config.get("openai") or {}).get("model") or "gpt-4o-mini-transcribe"))
        self.openai_key_var = tk.StringVar(value="")
        self.openai_key_status_var = tk.StringVar(value=self._openai_key_status_text())
        premium = self.config.get("premium") or {}
        self.premium_server_url_var = tk.StringVar(value=str(premium.get("server_url") or "https://golos.msgcrm.ru"))
        self.premium_key_var = tk.StringVar(value="")
        self.account_server_url = str(premium.get("server_url") or DEFAULT_ACCOUNT_SERVER_URL)
        self.premium_key_status_var = tk.StringVar(value=self._premium_key_status_text())
        self.premium_balance_var = tk.StringVar(value="Баланс не проверялся.")
        self.account_email_var = tk.StringVar(value=account_email_from_env())
        self.account_password_var = tk.StringVar(value="")
        self.account_name_var = tk.StringVar(value="")
        self.account_status_var = tk.StringVar(value=self._account_status_text())
        self.account_balance_var = tk.StringVar(value="Баланс не проверялся.")
        self.account_payment_amount_var = tk.StringVar(value="100")
        self.header_account_var = tk.StringVar(value=self._header_account_text())
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
        self.support_server_url_var = tk.StringVar(value=str(support.get("server_url") or DEFAULT_ACCOUNT_SERVER_URL))
        self.support_status_var = tk.StringVar(value=self._support_status_text())
        self.support_message_text: tk.Text | None = None
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

    def _set_window_icon(self) -> None:
        icon_path = asset_path("golos.ico")
        if not icon_path.exists():
            return
        try:
            self.root.iconbitmap(str(icon_path))
        except tk.TclError:
            pass

    def _logo_widget(self, parent: tk.Widget, size: int = 48) -> tk.Widget:
        try:
            from PIL import ImageTk

            self.logo_photo = ImageTk.PhotoImage(create_logo_image(size))
            return tk.Label(parent, image=self.logo_photo, bg=COLORS["nav"])
        except Exception:  # noqa: BLE001
            mark = tk.Canvas(parent, width=size, height=size, bg=COLORS["nav"], highlightthickness=0)
            pad = max(4, size // 10)
            mark.create_rectangle(pad, pad, size - pad, size - pad, fill=COLORS["green"], outline=COLORS["yellow"], width=2)
            mark.create_oval(size * 0.39, size * 0.18, size * 0.61, size * 0.56, fill="white", outline="white")
            mark.create_rectangle(size * 0.45, size * 0.54, size * 0.55, size * 0.78, fill="white", outline="white")
            mark.create_line(size * 0.31, size * 0.78, size * 0.69, size * 0.78, fill="white", width=3)
            return mark

    def _scrollable_tab(self, notebook: ttk.Notebook) -> tuple[ttk.Frame, ttk.Frame]:
        outer = ttk.Frame(notebook)
        canvas = tk.Canvas(outer, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding=18)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def resize_content(event: tk.Event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        def update_scroll_region(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Configure>", resize_content)
        content.bind("<Configure>", update_scroll_region)
        canvas.bind("<MouseWheel>", on_mousewheel)
        content.bind("<MouseWheel>", on_mousewheel)
        return outer, content

    def _build(self) -> None:
        header = tk.Frame(self.root, bg=COLORS["nav"], height=88)
        header.pack(fill="x")
        header.pack_propagate(False)

        self._logo_widget(header, 48).pack(side="left", padx=(24, 14), pady=20)

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

        account_status = tk.Label(
            header,
            textvariable=self.header_account_var,
            bg="#fff7c2",
            fg=COLORS["ink"],
            padx=14,
            pady=7,
            font=("Segoe UI", 10, "bold"),
        )
        account_status.pack(side="right", padx=(0, 10))

        body = ttk.Frame(self.root, padding=(24, 20, 24, 16))
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Настройки", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(body, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", pady=(2, 14))

        notebook = ttk.Notebook(body)
        notebook.pack(fill="both", expand=True)

        main_outer, main_tab = self._scrollable_tab(notebook)
        account_outer, account_tab = self._scrollable_tab(notebook)
        recognition_outer, recognition_tab = self._scrollable_tab(notebook)
        support_outer, support_tab = self._scrollable_tab(notebook)
        updates_outer, updates_tab = self._scrollable_tab(notebook)

        notebook.add(main_outer, text="Главное")
        notebook.add(account_outer, text="Аккаунт")
        notebook.add(recognition_outer, text="Распознавание")
        notebook.add(support_outer, text="Поддержка")
        notebook.add(updates_outer, text="Обновления")

        self._build_main_tab(main_tab)
        self._build_account_tab(account_tab)
        self._build_recognition_tab(recognition_tab)
        self._build_support_tab(support_tab)
        self._build_updates_tab(updates_tab)

        footer = ttk.Frame(body)
        footer.pack(fill="x", pady=(12, 0))
        footer_left = ttk.Frame(footer)
        footer_left.pack(side="left", fill="x", expand=True)
        footer_right = ttk.Frame(footer)
        footer_right.pack(side="right")
        ttk.Button(footer_left, text="Перезапустить", command=self._request_restart).pack(side="left")
        ttk.Button(footer_left, text="Ярлыки Windows", command=self._create_shortcuts_now).pack(side="left", padx=(8, 0))
        ttk.Button(footer_left, text="Сайт", command=self._open_site).pack(side="left", padx=(8, 0))
        ttk.Button(footer_right, text="Закрыть", command=self.root.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer_right, text="Сохранить", style="Accent.TButton", command=self._save).pack(side="right")

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
        site_box = ttk.Frame(panel, style="Panel.TFrame")
        ttk.Button(site_box, text="Открыть сайт Голос", command=self._open_site).pack(side="left")
        ttk.Label(site_box, text=PUBLIC_SITE_URL, style="Panel.TLabel").pack(side="left", padx=(10, 0))
        self._field(panel, 6, "Сайт", site_box)
        panel.columnconfigure(1, weight=1)

    def _build_account_tab(self, parent: ttk.Frame) -> None:
        panel = self._panel(parent)
        ttk.Label(panel, text="Аккаунт Голос", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        tk.Label(
            panel,
            textvariable=self.account_status_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=590,
        ).grid(row=1, column=1, sticky="w", pady=(0, 10))
        self._field(panel, 2, "Email", ttk.Entry(panel, textvariable=self.account_email_var, width=42))
        self._field(panel, 3, "Имя", ttk.Entry(panel, textvariable=self.account_name_var, width=42))
        self._field(panel, 4, "Пароль", ttk.Entry(panel, textvariable=self.account_password_var, show="*", width=42))

        account_buttons = ttk.Frame(panel, style="Panel.TFrame")
        account_buttons.grid(row=5, column=1, sticky="w", pady=(4, 14))
        ttk.Button(account_buttons, text="Войти", style="Accent.TButton", command=self._account_login).pack(side="left")
        ttk.Button(account_buttons, text="Зарегистрироваться", command=self._account_register).pack(side="left", padx=(10, 0))
        ttk.Button(account_buttons, text="Выйти", command=self._account_logout).pack(side="left", padx=(10, 0))

        tk.Label(
            panel,
            textvariable=self.account_balance_var,
            bg=COLORS["panel"],
            fg=COLORS["ink"],
            justify="left",
            wraplength=590,
            font=("Segoe UI", 11, "bold"),
        ).grid(row=6, column=1, sticky="w", pady=(0, 10))

        payment_box = ttk.Frame(panel, style="Panel.TFrame")
        ttk.Entry(payment_box, textvariable=self.account_payment_amount_var, width=10).pack(side="left")
        ttk.Label(payment_box, text="руб.", style="Panel.TLabel").pack(side="left", padx=(6, 12))
        ttk.Button(payment_box, text="Пополнить", style="Accent.TButton", command=self._account_create_payment).pack(side="left")
        ttk.Button(payment_box, text="Обновить баланс", command=self._account_refresh).pack(side="left", padx=(10, 0))
        self._field(panel, 7, "Пополнение", payment_box)
        tk.Label(
            panel,
            text="Оплата открывается на защищённой странице платёжной системы. Данные карт в программе Голос не вводятся и не хранятся.",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=590,
        ).grid(row=8, column=1, sticky="w", pady=(4, 0))
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

        premium_box = ttk.Frame(panel, style="Panel.TFrame")
        ttk.Button(premium_box, text="Проверить баланс", command=self._check_premium_balance).pack(side="left")
        self._field(panel, 7, "Премиум Голос", premium_box)
        tk.Label(
            panel,
            textvariable=self.premium_key_status_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=590,
        ).grid(row=8, column=1, sticky="w", pady=(0, 4))
        tk.Label(
            panel,
            textvariable=self.premium_balance_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=590,
        ).grid(row=9, column=1, sticky="w", pady=(0, 8))

        info = tk.Label(
            panel,
            textvariable=self.profile_info_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=590,
        )
        info.grid(row=10, column=1, sticky="w", pady=(10, 0))
        panel.columnconfigure(1, weight=1)
        profile_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_recognition_profile_ui())
        self._refresh_recognition_profile_ui()

    def _build_support_tab(self, parent: ttk.Frame) -> None:
        panel = self._panel(parent)
        ttk.Label(panel, text="Поддержка", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        tk.Label(
            panel,
            textvariable=self.support_status_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=590,
        ).grid(row=1, column=1, sticky="w", pady=(0, 12))

        message_box = tk.Text(
            panel,
            height=5,
            width=56,
            wrap="word",
            bg="#ffffff",
            fg=COLORS["ink"],
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 10),
        )
        self.support_message_text = message_box
        self._field(panel, 2, "Сообщение", message_box)

        buttons = ttk.Frame(panel, style="Panel.TFrame")
        buttons.grid(row=3, column=1, sticky="w", pady=(4, 0))
        ttk.Button(buttons, text="Отправить обращение", style="Accent.TButton", command=self._prepare_support_request).pack(side="left")
        ttk.Button(buttons, text="Сообщения поддержки", command=self._check_support_actions).pack(side="left", padx=(10, 0))
        ttk.Button(buttons, text="Сайт", command=self._open_site).pack(side="left", padx=(10, 0))

        tech_panel = ttk.Frame(panel, style="Panel.TFrame")
        tech_panel.grid(row=4, column=1, sticky="w", pady=(14, 0))
        ttk.Button(tech_panel, text="Открыть лог", command=self._open_log).pack(side="left")
        ttk.Button(tech_panel, text="Собрать диагностику вручную", command=self._collect_diagnostics).pack(side="left", padx=(10, 0))
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
        if self.text_correction_enabled_var.get() and not text_correction_model:
            messagebox.showerror("Голос", "Укажите модель исправления.")
            return
        if (profile == "openai" or self.text_correction_enabled_var.get()) and not (openai_key or self._openai_key_exists()):
            messagebox.showerror("Голос", "Для OpenAI-режима вставьте API-ключ OpenAI на вкладке распознавания.")
            return
        if profile == "premium" and not self._premium_key_exists():
            messagebox.showerror("Голос", "Для премиум-режима войдите в аккаунт Голос на вкладке «Аккаунт».")
            return

        try:
            openai_key_saved = self._save_openai_key_if_needed(openai_key)
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
        raw.setdefault("premium", {})["server_url"] = self.account_server_url
        raw.setdefault("premium", {})["license_key_env"] = PREMIUM_KEY_NAME
        raw.setdefault("text_correction", {})["enabled"] = bool(self.text_correction_enabled_var.get())
        raw.setdefault("text_correction", {})["model"] = text_correction_model
        raw.setdefault("feedback", {})["beep_on_recording"] = bool(self.beep_var.get())
        raw.setdefault("startup", {})["run_on_windows_startup"] = bool(self.autostart_var.get())
        raw.setdefault("support", {})["server_url"] = self.support_server_url_var.get().strip() or DEFAULT_ACCOUNT_SERVER_URL
        raw.setdefault("support", {})["token_env"] = str((self.config.get("support") or {}).get("token_env") or "GOLOS_SUPPORT_TOKEN")

        self.config_manager._write_yaml_mapping(raw)
        self.raw_config = raw
        self.config = deep_merge(DEFAULT_CONFIG_DATA, raw)
        self._apply_shortcuts()
        self.support_status_var.set(self._support_status_text())
        if openai_key_saved:
            self.openai_key_status_var.set(self._openai_key_status_text())
        self.premium_key_status_var.set(self._premium_key_status_text())
        self.header_account_var.set(self._header_account_text())
        self.status_var.set("Сохранено. Для применения горячей клавиши и профиля перезапустите Голос.")
        message = "Настройки сохранены."
        if openai_key_saved:
            message += "\n\nOpenAI API-ключ сохранён локально на этом компьютере."
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
        return (
            "Напишите, что произошло, и отправьте обращение. Голос приложит безопасные технические данные: "
            "версию, настройки без секретов и последние ошибки. Аудио, пароли, API-ключи и текст диктовки не отправляются."
        )

    def _account_status_text(self) -> str:
        email = account_email_from_env()
        if account_token_exists():
            return f"Вход выполнен: {email or 'аккаунт Голос'}."
        return "Войдите или зарегистрируйтесь, чтобы видеть баланс и пополнять Голос Премиум."

    def _header_account_text(self) -> str:
        email = account_email_from_env()
        if account_token_exists():
            return f"Аккаунт: {email or 'вход выполнен'}"
        return "Аккаунт: вход"

    def _account_login(self) -> None:
        email = self.account_email_var.get().strip()
        password = self.account_password_var.get()
        if not email or not password:
            messagebox.showerror("Голос", "Введите email и пароль.")
            return
        self._run_account_worker(
            "Выполняю вход...",
            lambda: login_account(self.account_server_url, email, password),
            self._handle_account_session,
        )

    def _account_register(self) -> None:
        email = self.account_email_var.get().strip()
        password = self.account_password_var.get()
        name = self.account_name_var.get().strip()
        if not email or not password:
            messagebox.showerror("Голос", "Введите email и пароль.")
            return
        self._run_account_worker(
            "Создаю аккаунт...",
            lambda: register_account(self.account_server_url, email, password, name),
            self._handle_account_session,
        )

    def _account_refresh(self) -> None:
        if not account_token_exists():
            messagebox.showinfo("Голос", "Сначала войдите в аккаунт.")
            return
        self._run_account_worker(
            "Обновляю баланс...",
            lambda: fetch_account(self.account_server_url),
            self._show_account_info,
        )

    def _account_create_payment(self) -> None:
        if not account_token_exists():
            messagebox.showinfo("Голос", "Сначала войдите в аккаунт.")
            return
        try:
            amount_rub = int(self.account_payment_amount_var.get().strip())
        except ValueError:
            messagebox.showerror("Голос", "Введите сумму пополнения в рублях.")
            return
        self._run_account_worker(
            "Создаю платёж...",
            lambda: create_account_payment(self.account_server_url, amount_rub),
            self._handle_account_payment,
        )

    def _account_logout(self) -> None:
        self._run_account_worker(
            "Выхожу из аккаунта...",
            lambda: logout_account(self.account_server_url),
            lambda _result: self._after_account_logout(),
        )

    def _run_account_worker(self, status: str, worker, on_success) -> None:  # noqa: ANN001
        self.account_status_var.set(status)

        def target() -> None:
            try:
                result = worker()
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: self._show_account_error(exc))
                return
            self.root.after(0, lambda: on_success(result))

        threading.Thread(target=target, name="golos-account", daemon=True).start()

    def _handle_account_session(self, session) -> None:  # noqa: ANN001
        save_account_session(session.account.email, session.token)
        self.account_password_var.set("")
        self._show_account_info(session.account)
        self.account_status_var.set(f"Вход выполнен: {session.account.email}.")
        self.premium_key_status_var.set(self._premium_key_status_text())
        self.header_account_var.set(self._header_account_text())
        messagebox.showinfo("Голос", "Аккаунт подключён. Премиум-доступ будет использоваться автоматически.")

    def _show_account_info(self, account) -> None:  # noqa: ANN001
        self.account_email_var.set(getattr(account, "email", self.account_email_var.get()))
        self.account_name_var.set(getattr(account, "name", self.account_name_var.get()))
        balance = float(getattr(account, "balance_minutes", 0.0) or 0.0)
        granted = float(getattr(account, "total_granted_minutes", 0.0) or 0.0)
        used = float(getattr(account, "total_used_minutes", 0.0) or 0.0)
        self.account_balance_var.set(f"Баланс: {balance:.1f} мин. Начислено: {granted:.1f} мин. Использовано: {used:.1f} мин.")
        self.premium_balance_var.set(self.account_balance_var.get())
        self.account_status_var.set(f"Вход выполнен: {getattr(account, 'email', '')}.")
        self.header_account_var.set(f"Баланс: {balance:.1f} мин.")

    def _handle_account_payment(self, payment) -> None:  # noqa: ANN001
        if getattr(payment, "error_message", ""):
            self.account_status_var.set("Платёж не создан.")
            messagebox.showerror("Голос", getattr(payment, "error_message"))
            return
        payment_url = getattr(payment, "payment_url", "")
        if not payment_url:
            self.account_status_var.set("Платёж создан, но ссылка не получена.")
            messagebox.showerror("Голос", "Сервер не вернул ссылку на оплату.")
            return
        self.account_status_var.set("Платёж создан. Открываю страницу оплаты...")
        self._open_url(payment_url)
        messagebox.showinfo("Голос", "После оплаты вернитесь сюда и нажмите «Обновить баланс».")

    def _after_account_logout(self) -> None:
        clear_account_session()
        self.account_password_var.set("")
        self.account_status_var.set(self._account_status_text())
        self.account_balance_var.set("Баланс не проверялся.")
        self.premium_balance_var.set("Баланс не проверялся.")
        self.premium_key_status_var.set(self._premium_key_status_text())
        self.header_account_var.set(self._header_account_text())

    def _show_account_error(self, exc: Exception) -> None:
        self.account_status_var.set("Ошибка аккаунта.")
        messagebox.showerror("Голос", f"Не удалось выполнить действие: {exc}")

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
        if account_token_exists():
            return "Премиум Голос подключён через аккаунт. Баланс и пополнение находятся на вкладке «Аккаунт»."
        if premium_env_value_exists(self._premium_settings_from_ui()):
            return "Премиум Голос подключён на этом компьютере."
        return "Для режима «Премиум Голос» войдите в аккаунт и пополните баланс."

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
                lambda: self._show_premium_balance_result(balance),
            )

        threading.Thread(target=worker, name="check-premium-balance", daemon=True).start()

    def _show_premium_balance_result(self, balance) -> None:  # noqa: ANN001
        text = f"Осталось {balance.balance_minutes:.1f} мин. Начислено {balance.total_granted_minutes:.1f} мин."
        self.premium_balance_var.set(text)
        self.account_balance_var.set(text)
        self.header_account_var.set(f"Баланс: {balance.balance_minutes:.1f} мин.")

    def _premium_settings_from_ui(self) -> PremiumSettings:
        premium = self.config.get("premium") or {}
        return PremiumSettings(
            server_url=self.account_server_url or str(premium.get("server_url") or "https://golos.msgcrm.ru"),
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
            account_token = account_token_from_env()
            if not server_url and (premium_key or account_token):
                server_url = self._premium_settings_from_ui().server_url
            if not server_url:
                server_url = DEFAULT_ACCOUNT_SERVER_URL
            user_message = self._support_message()
            if server_url:
                result = upload_support_package(
                    package,
                    server_url,
                    support_token_from_env(str(support.get("token_env") or "GOLOS_SUPPORT_TOKEN")),
                    metadata={
                        "profile": str(self.config.get("recognition_profile") or ""),
                        "backend": str(self.config.get("backend") or ""),
                        "message": user_message,
                    },
                    premium_key=premium_key,
                    account_token=account_token,
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

    def _support_message(self) -> str:
        if self.support_message_text is None:
            return ""
        return self.support_message_text.get("1.0", "end").strip()

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
                        account_token=account_token_from_env(),
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

    def _open_site(self) -> None:
        self._open_url(PUBLIC_SITE_URL)

    def _open_github(self) -> None:
        self._open_url(GITHUB_URL)

    @staticmethod
    def _open_url(url: str) -> None:
        try:
            os.startfile(url)  # noqa: S606 - Windows desktop helper.
        except (AttributeError, OSError):
            webbrowser.open(url)

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
            return f"OpenAI напрямую с этого компьютера. Нужен личный API-ключ OpenAI. Модель: {self.openai_model_var.get()}."
        if profile == "server":
            server_stt = self.config.get("server_stt") or {}
            server_url = str(server_stt.get("server_url") or "https://golos.msgcrm.ru")
            model = str(server_stt.get("model") or "base")
            return f"Через сервер Голос: {server_url}. Локальная серверная модель: {model}. OpenAI не используется."
        if profile == "premium":
            return "Через сервер Голос Премиум. Нужен вход в аккаунт, минуты списываются с баланса."
        return f"{LOCAL_MODEL_NAMES.get(profile, 'Локальная модель')}. Работает на вашем Windows-компьютере без отправки аудио в интернет."

    def _correction_model_text(self, enabled: bool) -> str:
        if enabled:
            return f"GPT исправляет готовый текст: {self.text_correction_model_var.get()}."
        return "Не используется. Текст вставляется сразу после распознавания."


def open_settings_window(config_path: str | Path = "config.yaml") -> None:
    SettingsWindow(config_path).run()
