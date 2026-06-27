from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from voice_input.config import ConfigManager, DEFAULT_CONFIG_DATA, deep_merge
from voice_input.diagnostics import collect_diagnostics
from voice_input.logger import DEFAULT_LOG_PATH
from voice_input.paths import resolve_runtime_path


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


class SettingsWindow:
    def __init__(self, config_path: str | Path = "config.yaml") -> None:
        self.config_manager = ConfigManager(config_path)
        self.raw_config = self.config_manager._read_yaml_mapping()
        self.config = deep_merge(DEFAULT_CONFIG_DATA, self.raw_config)

        self.root = tk.Tk()
        self.root.title("Голос - настройки")
        self.root.geometry("880x620")
        self.root.minsize(760, 560)
        self.root.configure(bg=COLORS["bg"])

        self.hotkey_var = tk.StringVar(value=str(self.config.get("hotkey") or "F8"))
        self.profile_var = tk.StringVar(value=str(self.config.get("recognition_profile") or "base"))
        self.language_var = tk.StringVar(value=self._label_for_language(str(self.config.get("language") or "ru")))
        self.openai_model_var = tk.StringVar(value=str((self.config.get("openai") or {}).get("model") or "gpt-4o-mini-transcribe"))
        text_correction = self.config.get("text_correction") or {}
        self.text_correction_enabled_var = tk.BooleanVar(value=bool(text_correction.get("enabled", False)))
        self.text_correction_model_var = tk.StringVar(value=str(text_correction.get("model") or "gpt-5.4-mini"))
        self.beep_var = tk.BooleanVar(value=bool((self.config.get("feedback") or {}).get("beep_on_recording", True)))
        self.autostart_var = tk.BooleanVar(value=bool((self.config.get("startup") or {}).get("run_on_windows_startup", False)))
        self.status_var = tk.StringVar(value="Настройки загружены")

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
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=(14, 8), background=COLORS["yellow_soft"])
        style.map("TButton", background=[("active", COLORS["yellow"]), ("pressed", COLORS["yellow"])])
        style.configure("Accent.TButton", background=COLORS["green"], foreground="white")
        style.map("Accent.TButton", background=[("active", COLORS["green_dark"]), ("pressed", COLORS["green_dark"])])
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
        ttk.Checkbutton(panel, text="Звуковой сигнал при записи", variable=self.beep_var).grid(row=3, column=1, sticky="w", pady=8)
        autostart = ttk.Checkbutton(panel, text="Автозапуск Windows (следующий шаг)", variable=self.autostart_var)
        autostart.grid(row=4, column=1, sticky="w", pady=8)
        autostart.state(["disabled"])
        panel.columnconfigure(1, weight=1)

    def _build_recognition_tab(self, parent: ttk.Frame) -> None:
        panel = self._panel(parent)
        profiles = sorted(str(name) for name in (self.config.get("profiles") or {}))
        ttk.Label(panel, text="Распознавание", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self._field(panel, 1, "Профиль", ttk.Combobox(panel, textvariable=self.profile_var, values=profiles, state="readonly", width=22))
        self._field(panel, 2, "Модель распознавания GPT", ttk.Entry(panel, textvariable=self.openai_model_var, width=32))
        ttk.Checkbutton(panel, text="GPT исправляет ошибки после распознавания", variable=self.text_correction_enabled_var).grid(row=3, column=1, sticky="w", pady=8)
        self._field(panel, 4, "Модель исправления", ttk.Entry(panel, textvariable=self.text_correction_model_var, width=32))

        info = tk.Label(
            panel,
            text="Профиль base работает локально. Профиль openai отправляет аудио в OpenAI. Галочка исправления отправляет уже распознанный текст в GPT.",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=560,
        )
        info.grid(row=5, column=1, sticky="w", pady=(10, 0))
        panel.columnconfigure(1, weight=1)

    def _build_diagnostics_tab(self, parent: ttk.Frame) -> None:
        panel = self._panel(parent)
        ttk.Label(panel, text="Диагностика", style="Section.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Button(panel, text="Открыть лог", command=self._open_log).pack(anchor="w", pady=4)
        ttk.Button(panel, text="Собрать диагностику", style="Accent.TButton", command=self._collect_diagnostics).pack(anchor="w", pady=4)

    def _build_updates_tab(self, parent: ttk.Frame) -> None:
        panel = self._panel(parent)
        ttk.Label(panel, text="Обновления", style="Section.TLabel").pack(anchor="w", pady=(0, 12))
        tk.Label(
            panel,
            text="Проверка и установка обновлений через GitHub Releases будет добавлена следующим шагом.",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=560,
        ).pack(anchor="w")
        ttk.Button(panel, text="Открыть GitHub", command=self._open_github).pack(anchor="w", pady=(14, 0))

    def _field(self, parent: ttk.Frame, row: int, label: str, widget: tk.Widget) -> None:
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 18), pady=8)
        widget.grid(row=row, column=1, sticky="w", pady=8)

    def _save(self) -> None:
        hotkey = self.hotkey_var.get().strip()
        profile = self.profile_var.get().strip()
        language = LANGUAGE_OPTIONS.get(self.language_var.get(), "ru")
        openai_model = self.openai_model_var.get().strip()
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
        if not openai_model:
            messagebox.showerror("Голос", "Укажите модель распознавания GPT.")
            return
        if self.text_correction_enabled_var.get() and not text_correction_model:
            messagebox.showerror("Голос", "Укажите модель исправления.")
            return

        raw = self.config_manager._read_yaml_mapping()
        raw["hotkey"] = hotkey
        raw["language"] = language
        raw["recognition_profile"] = profile
        raw.setdefault("openai", {})["model"] = openai_model
        raw.setdefault("text_correction", {})["enabled"] = bool(self.text_correction_enabled_var.get())
        raw.setdefault("text_correction", {})["model"] = text_correction_model
        raw.setdefault("feedback", {})["beep_on_recording"] = bool(self.beep_var.get())

        self.config_manager._write_yaml_mapping(raw)
        self.status_var.set("Сохранено. Для применения горячей клавиши и профиля перезапустите Голос.")
        messagebox.showinfo("Голос", "Настройки сохранены.")

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

    def _open_github(self) -> None:
        os.startfile("https://github.com/koskin2007-eng/golos")  # noqa: S606 - Windows desktop helper.

    def _label_for_language(self, language: str) -> str:
        for label, code in LANGUAGE_OPTIONS.items():
            if code == language:
                return label
        return "Русский"


def open_settings_window(config_path: str | Path = "config.yaml") -> None:
    SettingsWindow(config_path).run()
