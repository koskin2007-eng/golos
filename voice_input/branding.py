from __future__ import annotations

import sys
from pathlib import Path


PUBLIC_SITE_URL = "https://golos.msgcrm.ru"
GITHUB_URL = "https://github.com/koskin2007-eng/golos"


def asset_path(name: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "voice_input" / "assets" / name
    return Path(__file__).resolve().parent / "assets" / name


def create_logo_image(size: int = 64):
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - runtime dependency check.
        raise RuntimeError("Pillow is required to render the Golos logo.") from exc

    image_path = asset_path("golos.png")
    if image_path.exists():
        image = Image.open(image_path).convert("RGBA")
        return image.resize((size, size), Image.Resampling.LANCZOS)

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = size / 64

    def xy(values: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        return tuple(round(value * scale) for value in values)  # type: ignore[return-value]

    draw.rounded_rectangle(xy((4, 4, 60, 60)), radius=round(14 * scale), fill="#164e2e")
    draw.rounded_rectangle(xy((9, 9, 55, 55)), radius=round(11 * scale), outline="#facc15", width=max(2, round(3 * scale)))
    draw.ellipse(xy((25, 13, 39, 36)), fill="#ffffff")
    draw.rounded_rectangle(xy((29, 33, 35, 48)), radius=round(3 * scale), fill="#ffffff")
    draw.line(xy((20, 48, 44, 48)), fill="#ffffff", width=max(3, round(4 * scale)))
    draw.arc(xy((18, 20, 46, 52)), start=35, end=145, fill="#86efac", width=max(2, round(3 * scale)))
    return image
