"""Интеграция с YouTube: поиск видео и открытие в браузере."""

import subprocess

from config import PROJECT_ROOT


def _yt_dlp_path():
    return str(PROJECT_ROOT / ".venv" / "bin" / "yt-dlp")


def open_youtube(query):
    """Ищет первое подходящее видео на YouTube и открывает его в Chrome."""
    try:
        result = subprocess.run(
            [
                _yt_dlp_path(),
                f"ytsearch1:{query}",
                "--print", "webpage_url",
                "--skip-download",
                "--no-warnings",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        urls = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip().startswith("https://www.youtube.com/watch")
        ]

        if not urls:
            return f"Не удалось найти видео на YouTube: {query}"

        subprocess.run([
            "open",
            "-a",
            "Google Chrome",
            urls[0],
        ])

        return f"Открыл видео на YouTube: {query}"

    except Exception as error:
        return f"Не удалось открыть YouTube: {error}"