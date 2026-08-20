"""Точка входа desktop-приложения Akira."""

import os
import sys
from pathlib import Path


def _redirect_paths():
    """Перенаправляет пути данных в Application Support при frozen-запуске."""
    if not getattr(sys, "frozen", False):
        return

    data_dir = Path.home() / "Library" / "Application Support" / "Akira"
    logs_dir = data_dir / "logs"

    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "screenshots").mkdir(parents=True, exist_ok=True)

    import config

    memory_name = Path(config.MEMORY_FILE).name
    permissions_name = Path(config.PERMISSIONS_FILE).name
    spotify_name = Path(config.SPOTIFY_TOKEN_FILE).name

    config.MEMORY_FILE = str(data_dir / memory_name)
    config.PERMISSIONS_FILE = str(data_dir / permissions_name)
    config.SPOTIFY_TOKEN_FILE = str(data_dir / spotify_name)
    config.LOG_DIR = logs_dir
    config.SCREENSHOT_DIR = logs_dir / "screenshots"


def _silence_stdout():
    """Windowed .app может не иметь консоли; `say`/print не должны падать."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def main():
    _silence_stdout()
    _redirect_paths()

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("Akira")
    app.setApplicationDisplayName("Akira")

    from desktop_app.proactive_window import ProactiveMainWindow

    window = ProactiveMainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
