"""Find a YouTube video with yt-dlp and open it without downloading media."""
import subprocess
from urllib.parse import urlparse

from capabilities.protocol import fail, ok
from execution_context import ExecutionCancelled, raise_if_execution_cancelled


def open_youtube(query):
    query = str(query or "").strip()
    if not query:
        return fail("empty_query", "Не указано, какое видео найти.")
    raise_if_execution_cancelled()
    try:
        from yt_dlp import YoutubeDL
        options = {"quiet": True, "no_warnings": True, "skip_download": True,
                   "extract_flat": "in_playlist", "socket_timeout": 10,
                   "retries": 0, "extractor_retries": 0}
        with YoutubeDL(options) as downloader:
            result = downloader.extract_info(f"ytsearch1:{query}", download=False)
        raise_if_execution_cancelled()
        entries = list((result or {}).get("entries") or [])
        if not entries:
            return fail("video_not_found", f"Не найдено видео: {query}")
        entry = entries[0] or {}
        url = entry.get("webpage_url") or entry.get("url") or ""
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"www.youtube.com", "youtube.com"} or parsed.path != "/watch":
            return fail("invalid_video_url", "Поиск не вернул ссылку на видео YouTube.")
        opened = subprocess.run(["open", "-a", "Google Chrome", url], capture_output=True, text=True, timeout=10)
        if opened.returncode:
            return fail("browser_open_failed", opened.stderr.strip() or "Не удалось открыть Chrome.")
        return ok(f"Открыл видео на YouTube: {entry.get('title') or query}", url=url)
    except ExecutionCancelled:
        raise
    except Exception as error:
        return fail("youtube_unavailable", str(error))
