from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from voice_input.vision.translator import VisionTranslationResult


def show_translation_result(result: VisionTranslationResult) -> None:
    root = tk.Tk()
    root.title("Голос — перевод экрана")
    root.geometry("700x560")
    root.minsize(520, 420)
    root.attributes("-topmost", True)
    root.configure(bg="#fbfbef")

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background="#fbfbef")
    style.configure("TLabel", background="#fbfbef", foreground="#172112", font=("Segoe UI", 10))
    style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#164e2e")
    style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=(12, 7))
    style.configure("Accent.TButton", background="#16a34a", foreground="white")
    style.map("Accent.TButton", background=[("active", "#0f7a3a"), ("pressed", "#0f7a3a")])

    body = ttk.Frame(root, padding=20)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="Перевод экрана", style="Title.TLabel").pack(anchor="w")
    ttk.Label(body, text=f"Язык: {result.source_language} • Модель: {result.model}").pack(anchor="w", pady=(2, 14))

    ttk.Label(body, text="Исходный текст").pack(anchor="w")
    source = tk.Text(body, height=8, wrap="word", font=("Segoe UI", 11), relief="solid", borderwidth=1)
    source.pack(fill="both", expand=True, pady=(4, 12))
    source.insert("1.0", result.source_text or "Текст не найден.")
    source.configure(state="disabled")

    ttk.Label(body, text="Перевод на русский").pack(anchor="w")
    translated = tk.Text(body, height=9, wrap="word", font=("Segoe UI", 12), relief="solid", borderwidth=1)
    translated.pack(fill="both", expand=True, pady=(4, 14))
    translated.insert("1.0", result.translated_text or "Перевод отсутствует.")
    translated.configure(state="disabled")

    status = tk.StringVar(value=f"Готово за {result.elapsed_ms / 1000:.1f} с")
    buttons = ttk.Frame(body)
    buttons.pack(fill="x")
    ttk.Label(buttons, textvariable=status).pack(side="left")

    def copy_translation() -> None:
        root.clipboard_clear()
        root.clipboard_append(result.translated_text)
        root.update()
        status.set("Перевод скопирован")

    ttk.Button(buttons, text="Закрыть", command=root.destroy).pack(side="right")
    ttk.Button(buttons, text="Копировать перевод", style="Accent.TButton", command=copy_translation).pack(side="right", padx=(0, 8))
    root.bind("<Escape>", lambda _event: root.destroy())
    root.mainloop()
