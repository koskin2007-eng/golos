from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from voice_input.paths import resolve_runtime_path


LOGGER_NAME = "voice_input"
DEFAULT_LOG_PATH = Path("logs/app.log")


def setup_logging(level: str = "INFO", log_path: str | Path = DEFAULT_LOG_PATH) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    if logger.handlers:
        for handler in logger.handlers:
            handler.setLevel(logger.level)
        return logger

    path = resolve_runtime_path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logger.level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logger.level)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
